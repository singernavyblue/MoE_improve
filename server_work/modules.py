import re
import json
import os
import time
import urllib.request
import urllib.error
import numpy as np
from utils import generate_vllm, extract_numbers_as_ints, remove_boxed, last_boxed_only_string, parse_confidence_response
from copy import deepcopy
from loguru import logger

CONFIDENCE_THRESHOLD = 0.1  # Replace model if confidence < this or N/A

def generate_initial_response_with_confidence(
    model_id, endpoint, instruction, data=None, num_choice=4,
    temperature=0.7, max_tokens=800, seed=0, debug_txt=""
):
    """
    Generate initial response with confidence using JSON-formatted prompt.
    Returns (raw_response, answer, confidence, input_tokens, output_tokens)
    """

    # Build confidence-aware prompt
    if data in ['MATH', 'AIME24']:
        answer_format_hint = 'a mathematical expression or number (e.g., "42" or "3/4")'
    elif data in ['human_eval']:
        answer_format_hint = 'the completed Python function code'
    else:
        choices_str = ', '.join([chr(65 + i) for i in range(num_choice)])
        answer_format_hint = f'one of the answer choices: {choices_str}'

    confidence_instruction = (
        f"\n\nProvide brief reasoning (2-3 key sentences), then output your final answer in JSON format:\n"
        f'{{"reasoning": "<brief reasoning>", '
        f'"answer": "<{answer_format_hint}>", '
        f'"confidence_level": "<a float between 0.0 and 1.0>"}}\n'
        f"Please strictly output in JSON format."
    )

    augmented_instruction = instruction + confidence_instruction

    raw_response, _, _, i_t_c, o_t_c = generate_vllm(
        model=model_id,
        messages=[augmented_instruction],
        temperature=temperature,
        max_tokens=max_tokens,
        endpoint=endpoint,
        debug_txt=debug_txt,
        seed=seed
    )

    # Parse the response
    _, answer, confidence = parse_confidence_response(
        raw_response, data=data, num_choice=num_choice
    )

    return raw_response, answer, confidence, i_t_c, o_t_c


def maybe_replace_with_general(
    node_idx, node_name, confidence, models_dict, general_model_name,
    initial_responses, confidences, answers, sampled_nodes,
    instruction, data, num_choice, temperature, max_tokens, seed
):
    """
    If confidence is N/A (< 0) or below threshold, replace this node with general model.
    Returns (replaced, new_input_tokens, new_output_tokens)
    """
    should_replace = (confidence < 0) or (confidence < CONFIDENCE_THRESHOLD)

    if not should_replace:
        return False, 0, 0

    # Don't replace if this node IS the general model already
    if node_name == general_model_name:
        logger.info(f"[Confidence Replace] Node {node_idx} ({node_name}) has low confidence "
                     f"({confidence}) but is already the general model. Keeping.")
        return False, 0, 0

    logger.info(f"[Confidence Replace] Node {node_idx} ({node_name}) confidence={confidence:.3f} "
                 f"< {CONFIDENCE_THRESHOLD}. Replacing with {general_model_name}.")

    general_dict = models_dict[general_model_name]

    raw_response, answer, new_confidence, i_t_c, o_t_c = generate_initial_response_with_confidence(
        model_id=general_dict["model_id"],
        endpoint=general_dict["url"],
        instruction=instruction,
        data=data,
        num_choice=num_choice,
        temperature=temperature,
        max_tokens=max_tokens,
        seed=seed,
        debug_txt=f"[Replacement - {general_model_name} for {node_name}] "
    )

    initial_responses[node_idx] = raw_response
    confidences[node_idx] = new_confidence
    answers[node_idx] = answer
    sampled_nodes[node_idx] = general_model_name

    return True, i_t_c, o_t_c

def node_sampling_model_card(model, endpoint, messages, model_info_dict, top_k=4, temperature=0.7, max_tokens=512, seed=0):
    """
    Sample top-K relevant models based on the question and model descriptions.
    Simplified prompt: single combined instruction, no repeated criteria.
    """

    input_token_total = 0
    output_token_total = 0
    node_sampling_fallback = False

    try:
        model_descriptions = [{"index": idx, "description": model_info_dict[info]["model_card"]} for idx, info in enumerate(model_info_dict)]
        max_index = len(model_descriptions) - 1

        invalid_attempts = []

        if top_k == -1:
            # Determine difficulty to set top_k
            difficulty_prompt = {
                "role": "user",
                "content": (
                    f"Rate the difficulty of this question from 1 (very easy) to 6 (very hard).\n\n"
                    f"Question: {messages[0]}\n\n"
                    f"Reply with a single number only."
                )
            }

            difficulty_response, _, _, input_token_count, output_token_count = generate_vllm(
                model=model,
                endpoint=endpoint,
                messages=[difficulty_prompt],
                max_tokens=10,
                temperature=temperature,
                debug_txt="[Node Sampling - Difficulty] ",
                seed=seed
            )

            input_token_total += input_token_count
            output_token_total += output_token_count

            difficulty_level = extract_numbers_as_ints(difficulty_response)
            if difficulty_level and 1 <= difficulty_level[0] <= 6:
                top_k = difficulty_level[0]
            else:
                top_k = 3

            print(f"[Node Sampling] Determined Difficulty: {difficulty_level} → Selecting {top_k} models.")


        max_attempts = 5
        attempts = 0

        # Build example based on top_k
        example_dict = {
            1: "0",
            2: "0,3",
            3: "0,1,5",
            4: "0,0,4,5",
            5: "0,1,2,3,5",
            6: "0,0,2,3,4,5"
        }

        while attempts < max_attempts:
            # --- SIMPLIFIED PROMPT: single user message, concise criteria ---
            prompt_content = (
                f"Select {top_k} models best suited for this question.\n\n"
                f"Question: {messages[0]}\n\n"
                f"Available models:\n{json.dumps(model_descriptions, indent=None)}\n\n"
                f"Selection criteria (in priority order):\n"
                f"1. Domain match — prefer models trained in the question's domain\n"
                f"2. Task specialization — prefer models fine-tuned for the required skill\n"
                f"3. Include at least one generalist model if applicable\n"
                f"4. Prefer larger models only when the size gap is significant\n\n"
                f"Rules:\n"
                f"- Output exactly {top_k} comma-separated indices from [0, {max_index}]\n"
                f"- You may repeat an index if the model is highly relevant\n"
                f"- No explanations\n\n"
                f"Example: {example_dict[top_k]}\n\n"
                f"Answer:"
            )

            if invalid_attempts:
                prompt_content += f"\n(Previous invalid responses: {invalid_attempts}. Fix this.)"

            prompt = [{"role": "user", "content": prompt_content}]

            sampled_indices, _, _, input_token_count, output_token_count = generate_vllm(
                model=model,
                endpoint=endpoint,
                messages=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                debug_txt="[Node Sampling] ",
                seed=seed
            )

            input_token_total += input_token_count
            output_token_total += output_token_count

            # Validate extracted indices
            pattern = re.compile(
                r'</think>\s*([\d,]+)'
                r'|(?:Answer:\s*|the answer is:\s*\n?)(\d+)'
                r'|^\s*([\d,]+)\s*$',
                re.IGNORECASE | re.MULTILINE
            )

            match = pattern.search(sampled_indices)

            if match:
                extracted = match.group(1) or match.group(2) or match.group(3)

                if ',' in extracted:
                    sampled_indices = list(map(int, extracted.split(',')))
                else:
                    sampled_indices = [int(extracted)]

                if (0 <= np.array(sampled_indices)).all() and (np.array(sampled_indices) <= max_index).all():
                    break

            # Store invalid response for feedback in the next iteration
            attempts += 1
            invalid_attempts.append(sampled_indices)
            print(f"[Node Sampling] Invalid Answer: {sampled_indices}. Retrying...")


        if attempts == max_attempts:
            sampled_indices = list(np.arange(top_k))
            node_sampling_fallback = True
            print(f"[Node Sampling] Using fallback: selecting first {top_k} models")

        # Convert extracted indices to model names
        models_list = list(model_info_dict.keys())

        try:
            sampled_nodes = list(np.array(models_list)[sampled_indices])
        except Exception as e:
            print(f"Error mapping indices to models: {e}")
            sampled_nodes = [np.array(models_list)[0]]
            node_sampling_fallback = True

        return sampled_nodes, node_sampling_fallback, input_token_total, output_token_total

    except Exception as e:
        print(f"Error in node_sampling: {e}")
        return None


def parse_ranked_scores(text):
    text = text.strip()[:2000]

    # Case 1: Try to extract from a list-style bracketed structure like [0.7, 0.3]
    try:
        match = re.search(r'\[([0-9.,\s]+)\]', text)
        if match:
            tokens = re.split(r'[,\s]+', match.group(1))
            return [float(t) for t in tokens if t]
    except Exception as e:
        print(f"[parse_ranked_scores] List-style parsing error: {e}")

    # Case 2: Dictionary-style parsing like '0': 0.7, '1': 0.3 or * 1: 0.7
    try:
        dict_match = re.findall(r"[\*\-]?\s*'?(\d+)'?\s*:\s*([0-9]*\.?[0-9]+)", text)
        if dict_match:
            sorted_items = sorted([(int(k), float(v)) for k, v in dict_match], key=lambda x: x[0])
            return [v for _, v in sorted_items]
    except Exception as e:
        print(f"[parse_ranked_scores] Dict-style parsing error: {e}")

    # Case 3: Fallback - extract loose floats
    try:
        return [float(t) for t in re.split(r'[,\s]+', text) if t]
    except Exception as e:
        print(f"[parse_ranked_scores] Fallback parsing error: {e}")
        return []

def _parse_judge_score(text):
    """Parse the integer score (1-5) from Prometheus-style output."""
    if text is None:
        return None
    t = str(text)
    patterns = [
        r'###\s*Score\s*[:\-]?\s*([1-5](?:\.\d+)?)',
        r'[Ss]core\s*[:\-]?\s*([1-5](?:\.\d+)?)',
        r'[Ss]core[^0-9]{0,5}([1-5])\s*/\s*5',
        r'\[Result\]\s*([1-5](?:\.\d+)?)',
        r'overall score is\s*([1-5](?:\.\d+)?)',
        r'[Ss]core is\s*([1-5](?:\.\d+)?)',
        r'[Ss]core of\s*([1-5](?:\.\d+)?)',
        r'\[Result\]\s*:\s*([1-5](?:\.\d+)?)',
        r'rated?\s+([1-5])\s*/\s*5',
        r'([1-5])\s*out of\s*5',
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            try:
                f = float(m.group(1))
                return int(round(f)) if abs(f - round(f)) < 1e-9 else f
            except ValueError:
                pass
    # Fallback: the no-gold judge sometimes writes prose-only grading that
    # restates the rubric level without an explicit number. Map level phrases.
    t_lower = t.lower()
    prose_rules = [
        (r'every step of the reasoning is valid', 5),
        (r'leads coherently to the stated conclusion', 5),
        (r'mostly sound', 4),
        (r'only minor issues', 4),
        (r'substantive flaws', 3),
        (r'unjustified leaps', 3),
        (r'errors that cancel out', 3),
        (r'concrete factual', 2),
        (r'numerical, or logical errors', 2),
        (r'self-contradictory', 1),
        (r'irrelevant', 1),
        (r'empty', 1),
    ]
    for pat, s in prose_rules:
        if re.search(pat, t_lower):
            return s
    return None


def _parse_pairwise_result(text):
    """Parse the [RESULT] token of a pairwise judge call: 'A', 'B', or 'tie'."""
    if text is None:
        return None
    t = str(text).strip()
    m = re.search(r'\[RESULT\]\s*([A-Za-z]+)', t)
    if m:
        token = m.group(1).lower()
        if token.startswith('tie') or token in ('comparable', 'equal', 'similar', 'same', 'both', 'neither'):
            return 'tie'
        if token in ('a', 'a.', 'answer', 'responsea'):
            return 'A'
        if token in ('b', 'b.', 'answerb', 'responseb'):
            return 'B'
    # Prose fallbacks
    tl = t.lower()
    if 'response a is better' in tl or 'a is better' in tl or 'prefer response a' in tl or 'prefer a' in tl:
        return 'A'
    if 'response b is better' in tl or 'b is better' in tl or 'prefer response b' in tl or 'prefer b' in tl:
        return 'B'
    if any(k in tl for k in ('comparable', 'tie', 'equal quality', 'similar quality', 'both are of')):
        return 'tie'
    return None


def _parse_pairwise_margin(text):
    """Parse pairwise [RESULT] plus optional [PREFERENCE] strength token.

    Returns (result, margin): result in {'A','B','tie'}; margin is the winner's
    share of the pair in (0.5, 1.0] (the loser gets 1 - margin); a tie returns
    0.5. Defaults to 0.6 (slightly better) when no strength token is found.
    """
    result = _parse_pairwise_result(text)
    if result is None:
        return None, None
    if result == 'tie':
        return result, 0.5
    t = str(text or '').lower()
    m = re.search(r'\[preference\]\s*([^\n\]]+)', t)
    phrase = m.group(1).lower() if m else t
    if any(k in phrase for k in ('clearly better', 'much better', 'significantly better',
                                 'far better', 'obviously better', 'clearly')):
        margin = 0.85
    elif any(k in phrase for k in ('slightly better', 'marginally better', 'a little better',
                                   'somewhat better', 'slightly')):
        margin = 0.60
    elif any(k in phrase for k in ('better', 'stronger', 'prefer')):
        margin = 0.70
    elif any(k in phrase for k in ('comparable', 'tie', 'similar', 'equal', 'close')):
        return 'tie', 0.5
    else:
        margin = 0.60
    return result, margin


def _absolute_judge_scores(models, model_name_idx, initial_responses, messages,
                           judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                           total_scores, judge_count, fallback_used, score_matrix):
    """Prometheus absolute 1-5 grading of every response (original judge variant, no gold)."""
    rubric = (
        "Evaluate the reasoning chain of a response to a graduate-level science "
        "multiple-choice question. Give a single integer score from 1 to 5:\n"
        "1: The reasoning is irrelevant, empty, or self-contradictory.\n"
        "2: The reasoning contains concrete factual, numerical, or logical errors.\n"
        "3: The reasoning has substantive flaws (wrong facts, unjustified leaps, or errors that cancel out).\n"
        "4: The reasoning is mostly sound, with only minor issues.\n"
        "5: Every step of the reasoning is valid, well-supported, and leads coherently to the stated conclusion."
    )
    # Variant A: no gold/reference answer at deployment. The judge evaluates
    # reasoning quality on its own merits (no answer key leakage).
    reference_line = (
        "No reference answer is provided. Evaluate the response on its own merits."
    )

    input_token_count = 0
    output_token_count = 0

    for idx in models:
        response_text = initial_responses[idx]
        model_name = model_name_idx[idx]
        retry_count = 0
        judge_score = None

        while retry_count < max_retries:
            prompt_content = (
                "###Task Instruction:\n"
                f"{messages[0]}\n\n"
                "###Response to Evaluate:\n"
                f"{response_text}\n\n"
                "###Reference Answer (Score 5):\n"
                f"{reference_line}\n\n"
                "###Score Rubric:\n"
                f"{rubric}\n\n"
                "###Feedback:\n"
                "(Write a short feedback: which steps hold and which do not.)\n\n"
                "###Score:\n"
                "("
            )
            prompt = [{"role": "user", "content": prompt_content}]

            try:
                judge_output, _, _, i_t_c, o_t_c = generate_vllm(
                    model=judge_model_id,
                    endpoint=judge_url,
                    messages=prompt,
                    max_tokens=max_tokens,
                    temperature=0.2,
                    debug_txt=f"[Judge Edge Sampling - {model_name}]",
                    seed=seed
                )
                input_token_count += i_t_c
                output_token_count += o_t_c
                judge_score = _parse_judge_score(judge_output)
                if judge_score is not None:
                    break
                print(f"[Judge Edge Sampling - {model_name}] Invalid score output: {judge_output}")
            except Exception as e:
                print(f"[Judge Edge Sampling - {model_name}] Error: {e}")

            retry_count += 1
            print(f"[Judge Edge Sampling - {model_name}] Retrying ({retry_count}/{max_retries})...")

        if judge_score is None:
            print(f"[Judge Edge Sampling - {model_name}] Max retries reached. Using neutral score (response kept).")
            judge_score = 3.0
            fallback_used[idx] = True

        total_scores[idx] += judge_score
        judge_count[idx] += 1
        # Judge scores occupy row 0 of the score matrix (diagonal stays -1)
        score_matrix[0, idx] = judge_score
        print(f"[Judge Edge Sampling] {model_name} judge_score={judge_score}")

    return input_token_count, output_token_count, total_scores, judge_count, fallback_used


def _absolute_judge_scores_4dim_rubric(models, model_name_idx, initial_responses, messages,
                                       judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                                       total_scores, judge_count, fallback_used, score_matrix):
    """Strict control-variable variant of the absolute (no-gold) judge:
    identical pipeline and output (single 1-5 score), but the rubric text is the
    four ClawTrack-style dimensions instead of the single generic rubric.
    """
    rubric_4dim_abs = (
        "Evaluate the reasoning chain of a response to a graduate-level science "
        "multiple-choice question on four dimensions, then give a single integer "
        "score from 1 to 5 (overall quality, D1-gated):\n"
        "D1 Goal Alignment (gate): 5=correctly identifies the question type and respects "
        "every qualifier; 4=understands the question but misses one minor qualifier; "
        "3=understands the type but substitutes the goal midway; 2=answers a related but "
        "different question; 1=inverts the question type (e.g. an 'except' question "
        "answered with the wrong item).\n"
        "D2 Information Utilization: 5=every fact correct, all given numbers/conditions "
        "used, options checked one by one; 4=mostly correct, one non-critical condition "
        "missed; 3=conclusion correct but a substantive factual error (errors cancel out); "
        "2=wrong key fact/reagent/property drives the wrong conclusion; 1=ignores the "
        "given information or fabricates facts.\n"
        "D3 Result Verification: 5=explicit consistency check (conclusion vs reasoning, "
        "vs options, vs numbers); 4=consistent but no explicit check; 3=second-guesses "
        "but does not fully verify; 2=conclusion directly contradicts the chain's own "
        "reasoning and the model does not notice; 1=no verification, assertion without "
        "support, or an obviously impossible result.\n"
        "D4 Efficiency: 5=direct, complete, no filler; 4=minor redundancy; 3=one or two "
        "repeated arguments; 2=many detours, padding length to fake rigor; 1=pure "
        "restatement or corrupted output.\n"
        "Rules: score each dimension independently; length and confidence are NOT "
        "correctness; if D1 <= 2 the chain is failed overall regardless of D2-D4."
    )
    reference_line = (
        "No reference answer is provided. Evaluate the response on its own merits."
    )

    input_token_count = 0
    output_token_count = 0

    for idx in models:
        response_text = initial_responses[idx]
        model_name = model_name_idx[idx]
        retry_count = 0
        judge_score = None

        while retry_count < max_retries:
            prompt_content = (
                "###Task Instruction:\n"
                f"{messages[0]}\n\n"
                "###Response to Evaluate:\n"
                f"{response_text}\n\n"
                "###Reference Answer (Score 5):\n"
                f"{reference_line}\n\n"
                "###Score Rubric:\n"
                f"{rubric_4dim_abs}\n\n"
                "###Feedback:\n"
                "(Write a short feedback: which steps hold and which do not.)\n\n"
                "###Score:\n"
                "("
            )
            prompt = [{"role": "user", "content": prompt_content}]

            try:
                judge_output, _, _, i_t_c, o_t_c = generate_vllm(
                    model=judge_model_id,
                    endpoint=judge_url,
                    messages=prompt,
                    max_tokens=max_tokens,
                    temperature=0.2,
                    debug_txt=f"[Abs4DimRubric Judge - {model_name}]",
                    seed=seed
                )
                input_token_count += i_t_c
                output_token_count += o_t_c
                judge_score = _parse_judge_score(judge_output)
                if judge_score is not None:
                    break
                print(f"[Abs4DimRubric Judge - {model_name}] Invalid score output: {judge_output[:200]}")
            except Exception as e:
                print(f"[Abs4DimRubric Judge - {model_name}] Error: {e}")

            retry_count += 1
            print(f"[Abs4DimRubric Judge - {model_name}] Retrying ({retry_count}/{max_retries})...")

        if judge_score is None:
            print(f"[Abs4DimRubric Judge - {model_name}] Max retries reached. Using neutral score.")
            judge_score = 3.0
            fallback_used[idx] = True

        total_scores[idx] += judge_score
        judge_count[idx] += 1
        score_matrix[0, idx] = judge_score
        print(f"[Abs4DimRubric Judge] {model_name} judge_score={judge_score}")

    return input_token_count, output_token_count, total_scores, judge_count, fallback_used


def _parse_4dim_scores(text):
    """Parse an explicit four-dimension JSON score block like {"D1":4,"D2":3,"D3":2,"D4":4}.
    Tolerates surrounding prose. Returns dict {D1..D4} of ints 1-5 or None."""
    m = re.search(r"\{[^{}]*D1[^{}]*D2[^{}]*D3[^{}]*D4[^{}]*\}", text, re.I | re.S)
    if m is None:
        m = re.search(r"\{[^{}]*D1[^{}]*\}", text, re.I | re.S)
    data = None
    if m is not None:
        try:
            data = json.loads(m.group(0))
        except Exception:
            data = None
    if data is None:
        nums = re.findall(r"['\"]?D([1-4])['\"]?\s*[:=]\s*([0-5])", text, re.I)
        if len(nums) == 4:
            data = {f"D{d}": int(v) for d, v in nums}
    if data is None:
        return None
    out = {}
    for k in ("D1", "D2", "D3", "D4"):
        v = data.get(k)
        if isinstance(v, (int, float)) and 1 <= v <= 5:
            out[k] = int(v)
        else:
            return None
    return out


def _call_deepseek(prompt_content, api_key, model="deepseek-chat", max_tokens=600, retries=3):
    """Call the DeepSeek OpenAI-compatible chat API for judge prompts."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt_content}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                data = json.loads(r.read().decode())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[DeepSeek judge] call failed ({attempt+1}/{retries}): {e}")
            time.sleep(5 + attempt * 4)
    return ""


def _judge_4dim_scores(models, model_name_idx, initial_responses, messages,
                       judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                       total_scores, judge_count, fallback_used, score_matrix):
    """Explicit 4-dimension scores, combined by formula (no pairwise, no self-judged winner).

    Judge outputs JSON {D1,D2,D3,D4} for every chain; the edge weight is
    total = gate(D1) * (0.3*D2 + 0.5*D3 + 0.2*D4), gate(D1)=0 if D1<=2
    (goal-alignment veto). D3 (result verification) carries the largest weight
    because it is the systematic bottleneck in our GPQA experiments. Everything
    downstream (threshold, edges, message passing, pooling) is unchanged.
    """
    rubric_4dim = (
        "Score this reasoning chain on four independent dimensions, each 1 (worst) "
        "to 5 (best):\n"
        "D1 Goal Alignment (gate): 5=correctly identifies the question type and respects "
        "every qualifier; 4=understands the question but misses one minor qualifier; "
        "3=understands the type but substitutes the goal midway (e.g. switches from 'find "
        "the correct route' to 'find the closest option'); 2=answers a related but different "
        "question; 1=inverts the question type (e.g. an 'except' question answered with the "
        "wrong item).\n"
        "D2 Information Utilization: 5=every fact correct, all given numbers/conditions used, "
        "options checked one by one; 4=mostly correct, one non-critical condition missed; "
        "3=conclusion correct but a substantive factual error (errors cancel out); "
        "2=wrong key fact/reagent/property drives the wrong conclusion; 1=ignores the given "
        "information or fabricates facts.\n"
        "D3 Result Verification: 5=explicit consistency check (conclusion vs reasoning, vs "
        "options, vs numbers); 4=consistent but no explicit check; 3=second-guesses but does "
        "not fully verify; 2=conclusion directly contradicts the chain's own reasoning and "
        "the model does not notice; 1=no verification, assertion without support, or an "
        "obviously impossible result.\n"
        "D4 Efficiency: 5=direct, complete, no filler; 4=minor redundancy; 3=one or two "
        "repeated arguments; 2=many detours, padding length to fake rigor; 1=pure restatement "
        "or corrupted output.\n"
        "Rules: score each dimension independently; length and confidence are NOT correctness; "
        "if D1 <= 2 the chain is failed overall regardless of D2-D4."
    )
    reference_line = (
        "No reference answer is provided. Evaluate the response on its own merits."
    )

    input_token_count = 0
    output_token_count = 0

    for idx in models:
        response_text = initial_responses[idx]
        model_name = model_name_idx[idx]
        retry_count = 0
        dims = None

        while dims is None and retry_count < max_retries:
            prompt_content = (
                "###Task Instruction:\n"
                f"{messages[0]}\n\n"
                "###Response to Evaluate:\n"
                f"{response_text}\n\n"
                "###Reference Answer (Score 5):\n"
                f"{reference_line}\n\n"
                "###Score Rubric:\n"
                f"{rubric_4dim}\n\n"
                "###Feedback:\n"
                "(Write 2-3 sentences: which steps hold, which fail, and whether the "
                "conclusion is supported by the reasoning.)\n\n"
                "###Score JSON:\n"
                '{"D1": <1-5>, "D2": <1-5>, "D3": <1-5>, "D4": <1-5>}'
            )
            prompt = [{"role": "user", "content": prompt_content}]

            try:
                if judge_model_id == "deepseek":
                    judge_output = _call_deepseek(prompt_content, os.environ.get("DEEPSEEK_API_KEY", ""))
                else:
                    judge_output, _, _, i_t_c, o_t_c = generate_vllm(
                        model=judge_model_id,
                        endpoint=judge_url,
                        messages=prompt,
                        max_tokens=max_tokens,
                        temperature=0.2,
                        debug_txt=f"[4Dim Judge - {model_name}]",
                        seed=seed
                    )
                    input_token_count += i_t_c
                    output_token_count += o_t_c
                dims = _parse_4dim_scores(judge_output)
                if dims is not None:
                    break
                print(f"[4Dim Judge - {model_name}] Invalid JSON: {judge_output[:200]}")
            except Exception as e:
                print(f"[4Dim Judge - {model_name}] Error: {e}")

            retry_count += 1
            print(f"[4Dim Judge - {model_name}] Retrying ({retry_count}/{max_retries})...")

        if dims is None:
            print(f"[4Dim Judge - {model_name}] Max retries reached. Using neutral D1-D4=3.")
            dims = {"D1": 3, "D2": 3, "D3": 3, "D4": 3}
            fallback_used[idx] = True

        gate = 0.0 if dims["D1"] <= 2 else 1.0
        score = gate * (0.3 * dims["D2"] + 0.5 * dims["D3"] + 0.2 * dims["D4"])
        total_scores[idx] += score
        judge_count[idx] += 1
        score_matrix[0, idx] = score
        print(f"[4Dim Judge] {model_name} D1={dims['D1']} D2={dims['D2']} D3={dims['D3']} "
              f"D4={dims['D4']} -> score={score:.2f}")

    return input_token_count, output_token_count, total_scores, judge_count, fallback_used


def _absolute_judge_scores_theory_rubric(models, model_name_idx, initial_responses, messages,
                                         judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                                         total_scores, judge_count, fallback_used, score_matrix):
    """Strict control variable: absolute (no-gold) judge with the theory-grounded
    rubric (Toulmin completeness + SOLO structural ladder + Facione soundness).
    Identical pipeline/output (single 1-5 score) to the 4dim-rubric variant.
    """
    rubric_theory_abs = (
        "Evaluate the reasoning chain of a response to a graduate-level science "
        "multiple-choice question with a rubric grounded in argumentation theory "
        "(Toulmin), learning-outcome structure (SOLO), and critical-thinking "
        "assessment (Facione), then give a single integer score from 1 to 5.\n"
        "STEP 1 - COMPLETENESS (Toulmin six elements): Claim, Data, Warrant, Backing, "
        "Qualifier, Rebuttal. A complete chain states the final claim, uses correct "
        "data, and explains WHY the data support the claim (warrant). A chain with "
        "data but no warrant is incomplete no matter how long it is.\n"
        "STEP 2 - STRUCTURAL DEPTH (SOLO ladder, this IS the 1-5 scale):\n"
        "1 Prestructural: irrelevant, self-contradictory, or off-task.\n"
        "2 Unistructural/Multistructural: one or several correct points but no linking "
        "argument; conclusion missing, unsupported, or wrong.\n"
        "3 Multistructural with substantive error: conclusion plausible but the linking "
        "argument contains a factual or logical error.\n"
        "4 Relational: points linked into a coherent argument; the conclusion follows "
        "with only minor gaps.\n"
        "5 Extended abstract: the argument is complete, alternatives are checked, and "
        "the conclusion is verified.\n"
        "STEP 3 - RELIABILITY (Facione evaluation; logical soundness): check with your "
        "own scientific knowledge whether the premises are true, the inference is "
        "valid, the final answer is consistent with the reasoning and with the "
        "question's qualifiers (e.g., an 'except' question), and whether the chain "
        "notices and corrects its own mistakes.\n"
        "Scoring rule: start from the SOLO level (STEP 2); adjust by at most 1 based "
        "on STEP 3 (a sound short chain beats a long but wrong one; an internally "
        "consistent chain resting on a false premise cannot score above 3). "
        "Length and confidence are NOT correctness."
    )
    reference_line = (
        "No reference answer is provided. Evaluate the response on its own merits."
    )

    input_token_count = 0
    output_token_count = 0

    for idx in models:
        response_text = initial_responses[idx]
        model_name = model_name_idx[idx]
        retry_count = 0
        judge_score = None

        while retry_count < max_retries:
            prompt_content = (
                "###Task Instruction:\n"
                f"{messages[0]}\n\n"
                "###Response to Evaluate:\n"
                f"{response_text}\n\n"
                "###Reference Answer (Score 5):\n"
                f"{reference_line}\n\n"
                "###Score Rubric:\n"
                f"{rubric_theory_abs}\n\n"
                "###Feedback:\n"
                "(Write a short feedback: which steps hold and which do not.)\n\n"
                "###Score:\n"
                "("
            )
            prompt = [{"role": "user", "content": prompt_content}]

            try:
                judge_output, _, _, i_t_c, o_t_c = generate_vllm(
                    model=judge_model_id,
                    endpoint=judge_url,
                    messages=prompt,
                    max_tokens=max_tokens,
                    temperature=0.2,
                    debug_txt=f"[AbsTheoryRubric Judge - {model_name}]",
                    seed=seed
                )
                input_token_count += i_t_c
                output_token_count += o_t_c
                judge_score = _parse_judge_score(judge_output)
                if judge_score is not None:
                    break
                print(f"[AbsTheoryRubric Judge - {model_name}] Invalid score output: {judge_output[:200]}")
            except Exception as e:
                print(f"[AbsTheoryRubric Judge - {model_name}] Error: {e}")

            retry_count += 1
            print(f"[AbsTheoryRubric Judge - {model_name}] Retrying ({retry_count}/{max_retries})...")

        if judge_score is None:
            print(f"[AbsTheoryRubric Judge - {model_name}] Max retries reached. Using neutral score.")
            judge_score = 3.0
            fallback_used[idx] = True

        total_scores[idx] += judge_score
        judge_count[idx] += 1
        score_matrix[0, idx] = judge_score
        print(f"[AbsTheoryRubric Judge] {model_name} judge_score={judge_score}")

    return input_token_count, output_token_count, total_scores, judge_count, fallback_used


def _pairwise_copeland_scores(models, model_name_idx, initial_responses, messages,
                              judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                              total_scores, judge_count, fallback_used, score_matrix):
    """Prometheus pairwise comparison with Copeland counting (method A).

    Every pair of initial responses is compared by the judge once; the winner gets
    1.0 point, a tie gives 0.5 points to each, the loser gets 0.0. Raw points are
    averaged and normalized to sum to 1.0 downstream (exactly as the absolute
    judge variant).
    """
    pairwise_rubric = (
        "Compare the two reasoning chains for a graduate-level science multiple-choice "
        "question. Prefer the chain whose reasoning is more complete, factually accurate, "
        "logically sound, and leads coherently to a well-supported conclusion. Do not "
        "prefer a chain merely because it is longer or more confident."
    )
    reference_line = (
        "No reference answer is provided. Evaluate the two responses on their own merits."
    )

    input_token_count = 0
    output_token_count = 0
    n = len(models)

    for ai in range(n):
        for bi in range(ai + 1, n):
            key_a, key_b = models[ai], models[bi]
            name_a, name_b = model_name_idx[key_a], model_name_idx[key_b]
            resp_a, resp_b = initial_responses[key_a], initial_responses[key_b]
            pair_result = None
            retry_count = 0

            while pair_result is None and retry_count < max_retries:
                prompt_content = (
                    "###Task Description:\n"
                    "An instruction (might include an Input inside it), two responses to "
                    "evaluate (denoted as Response A and Response B), and an evaluation "
                    "criteria are given.\n"
                    "1. Write a detailed feedback that assesses the quality of the two "
                    "responses strictly based on the given evaluation criteria, not "
                    "evaluating in general.\n"
                    "2. Make comparisons between Response A and Response B. Go straight "
                    "to the point and mention the commonalities and differences between them.\n"
                    "3. After writing the feedback, indicate the better response: \"A\", "
                    "\"B\", or \"tie\" if they are of comparable quality.\n"
                    "4. The output format should look as follows: \"Feedback: (write a "
                    "feedback for criteria) [RESULT] (A, B, or tie)\"\n"
                    "5. Please do not generate any other opening, closing, and explanations.\n\n"
                    "###Instruction:\n"
                    f"{messages[0]}\n\n"
                    "###Response A:\n"
                    f"{resp_a}\n\n"
                    "###Response B:\n"
                    f"{resp_b}\n\n"
                    "###Reference Answer:\n"
                    f"{reference_line}\n\n"
                    "###Score Rubric:\n"
                    f"{pairwise_rubric}\n\n"
                    "###Feedback:\n"
                )
                prompt = [{"role": "user", "content": prompt_content}]

                try:
                    judge_output, _, _, i_t_c, o_t_c = generate_vllm(
                        model=judge_model_id,
                        endpoint=judge_url,
                        messages=prompt,
                        max_tokens=max_tokens,
                        temperature=0.2,
                        debug_txt=f"[Pairwise Judge - {name_a} vs {name_b}]",
                        seed=seed
                    )
                    input_token_count += i_t_c
                    output_token_count += o_t_c
                    pair_result = _parse_pairwise_result(judge_output)
                    if pair_result is not None:
                        break
                    print(f"[Pairwise Judge - {name_a} vs {name_b}] Invalid result: {judge_output[:200]}")
                except Exception as e:
                    print(f"[Pairwise Judge - {name_a} vs {name_b}] Error: {e}")

                retry_count += 1
                print(f"[Pairwise Judge - {name_a} vs {name_b}] Retrying ({retry_count}/{max_retries})...")

            if pair_result is None:
                print(f"[Pairwise Judge - {name_a} vs {name_b}] Max retries reached. Using tie.")
                pair_result = "tie"
                fallback_used[key_a] = True
                fallback_used[key_b] = True

            if pair_result == "A":
                total_scores[key_a] += 1.0
                score_matrix[ai, bi] = 1.0
                score_matrix[bi, ai] = 0.0
            elif pair_result == "B":
                total_scores[key_b] += 1.0
                score_matrix[ai, bi] = 0.0
                score_matrix[bi, ai] = 1.0
            else:  # tie
                total_scores[key_a] += 0.5
                total_scores[key_b] += 0.5
                score_matrix[ai, bi] = 0.5
                score_matrix[bi, ai] = 0.5

            judge_count[key_a] += 1
            judge_count[key_b] += 1
            print(f"[Pairwise Judge - {name_a} vs {name_b}] result={pair_result} | "
                  f"{name_a}:{total_scores[key_a]:.1f} {name_b}:{total_scores[key_b]:.1f}")

    return input_token_count, output_token_count, total_scores, judge_count, fallback_used


def _pairwise_margin_scores(models, model_name_idx, initial_responses, messages,
                            judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                            total_scores, judge_count, fallback_used, score_matrix, four_dim=False,
                            theory_rubric=False):
    """Prometheus pairwise comparison with margin weighting (method B).

    The judge compares every pair and reports both the winner ([RESULT] A/B/tie)
    and the strength ([PREFERENCE] clearly better / better / slightly better /
    comparable), mapped to winner margins 0.85 / 0.70 / 0.60 / 0.50. Each node's
    score is the average of its margins across pairs; normalized to sum to 1.0
    downstream exactly as the other variants.

    If four_dim=True, the judge first scores each chain on the four ClawTrack-style
    dimensions (goal alignment, information utilization, result verification,
    efficiency) with 1-5 behavioral anchors, then emits the same [RESULT] /
    [PREFERENCE] pair. Everything downstream is unchanged.

    If theory_rubric=True, the rubric is replaced by the theory-grounded version
    (Toulmin argument elements + SOLO structural ladder + Facione soundness checks).
    Everything downstream is unchanged. This is the controlled experiment against
    the short generic rubric (baseline pairwise_margin) and the 4-dim rubric.
    """
    pairwise_rubric = (
        "Compare the two reasoning chains for a graduate-level science multiple-choice "
        "question. Prefer the chain whose reasoning is more complete, factually accurate, "
        "logically sound, and leads coherently to a well-supported conclusion. Do not "
        "prefer a chain merely because it is longer or more confident."
    )
    rubric_4dim = (
        "Score each reasoning chain on four independent dimensions, 1 (worst) to 5 (best).\n"
        "\n"
        "D1 Goal Alignment (gate dimension):\n"
        "5: correctly identifies the question type (calculation/judgment/except/structure) "
        "and respects every qualifier.\n"
        "4: understands the question but misses one minor qualifier.\n"
        "3: understands the question type but substitutes the goal midway (e.g., switches "
        "from 'find the correct route' to 'find the closest option').\n"
        "2: answers a related but different question (e.g., asked for the structure of "
        "product 4 but only argues the starting configuration).\n"
        "1: inverts the question type (e.g., an 'except' question answered with the wrong "
        "item) or answers a different question.\n"
        "\n"
        "D2 Information Utilization (domain knowledge / given conditions / options):\n"
        "5: every chemical/physical/biological fact is correct, all given numbers and "
        "conditions are used, and options are checked one by one.\n"
        "4: facts are mostly correct; one non-critical condition or option is missed.\n"
        "3: conclusion is correct but the reasoning contains a substantive factual error "
        "(errors that cancel out).\n"
        "2: invokes a wrong key fact/reagent/property, which drives the wrong conclusion.\n"
        "1: basically ignores the given information or fabricates facts.\n"
        "\n"
        "D3 Result Verification (consistency check before committing):\n"
        "5: performs an explicit consistency check: conclusion vs reasoning, conclusion "
        "vs options, numbers vs question.\n"
        "4: reasoning and conclusion are consistent but no explicit check is performed.\n"
        "3: second-guesses or revises itself but does not fully verify; final conclusion "
        "is consistent with the reasoning.\n"
        "2: the conclusion directly contradicts the chain's own reasoning and the model "
        "does not notice.\n"
        "1: no verification at all; conclusion asserted without support, or an obviously "
        "impossible result given confidently.\n"
        "\n"
        "D4 Efficiency (redundancy only; short-but-wrong is as wrong as long-but-wrong):\n"
        "5: direct, complete, no filler; every sentence advances the reasoning.\n"
        "4: minor redundancy that does not hurt understanding.\n"
        "3: one or two repeated arguments or non-progress paragraphs.\n"
        "2: many detours: restating the question, restarting repeatedly, padding length "
        "to fake rigor.\n"
        "1: pure restatement of the question with no content, or a badly corrupted output.\n"
        "\n"
        "Rules:\n"
        "- Score each dimension independently; do NOT give all four dimensions the same "
        "score because of one overall impression (anti-halo).\n"
        "- Length and confidence are NOT correctness.\n"
        "- A chain scoring 1-2 on Goal Alignment cannot score above 2 overall.\n"
        "- Then compare the two chains dimension by dimension, prioritizing D1, then D3, "
        "then D2, then D4, and decide which chain is better."
    )
    rubric_toulmin_solo = (
        "Evaluate the two reasoning chains with a rubric grounded in argumentation "
        "theory (Toulmin), learning-outcome structure (SOLO), critical-thinking "
        "assessment (Facione), and evidence-centered design (Mislevy). Use the four "
        "dimensions below as a checklist to see where the chains differ, then apply "
        "the decision rule to pick the winner.\n"
        "\n"
        "D1 QUESTION ALIGNMENT (Facione interpretation/analysis; ECD task model).\n"
        "Does the chain answer the question that was actually asked?\n"
        "5: correctly identifies the question type (calculation/judgment/except/structure) "
        "and respects every qualifier; the final claim answers exactly what was asked.\n"
        "4: understands the question but misses one minor qualifier.\n"
        "3: understands the question type but substitutes the goal midway (e.g., asked "
        "for the structure of product 4 but argues only the starting configuration).\n"
        "2: answers a related but different question (e.g., an 'except' question argued "
        "as if selecting the correct statement).\n"
        "1: inverts the question type (an 'except' question answered with the correct "
        "item) or answers a completely different question.\n"
        "\n"
        "D2 EVIDENCE AND WARRANT (Toulmin Data + Warrant + Backing).\n"
        "Does the chain use correct evidence AND explain why the evidence supports "
        "the claim?\n"
        "5: every fact correct, all numbers/conditions used, options checked one by one, "
        "and the chain states WHY the data support the claim (warrant); non-trivial "
        "inferences carry backing.\n"
        "4: facts mostly correct; one non-critical condition or option missed; warrant "
        "present but implicit.\n"
        "3: conclusion plausible but the reasoning contains a substantive factual or "
        "logical error (e.g., errors that cancel out), OR correct facts with no warrant "
        "(data listed but the link to the claim is unexplained).\n"
        "2: a wrong key fact/reagent/property drives the wrong conclusion.\n"
        "1: ignores the given information or fabricates facts.\n"
        "\n"
        "D3 VERIFICATION AND SOUNDNESS (Facione evaluation + self-regulation; "
        "logical soundness).\n"
        "Is the inference valid, are the premises true, and is the conclusion consistent?\n"
        "5: performs an explicit check - conclusion vs reasoning, conclusion vs options, "
        "numbers vs question - and notices/corrects any slip (self-regulation).\n"
        "4: reasoning and conclusion consistent, but no explicit check performed.\n"
        "3: second-guesses itself but does not fully verify; final conclusion consistent "
        "with the reasoning, or internally consistent but resting on a false premise.\n"
        "2: the conclusion directly contradicts the chain's own reasoning, unnoticed.\n"
        "1: no verification; conclusion asserted without support, or an obviously "
        "impossible result given confidently.\n"
        "\n"
        "D4 STRUCTURAL DEPTH AND EFFICIENCY (SOLO ladder; Toulmin relevance).\n"
        "How complete is the argument structure, without padding?\n"
        "5 Extended abstract: argument complete, alternatives/rebuttals checked, no filler.\n"
        "4 Relational: points linked into a coherent argument; only minor gaps; minor "
        "redundancy allowed.\n"
        "3 Multistructural: several relevant points but the linking argument is missing "
        "or gappy; one or two repeated arguments.\n"
        "2 Unistructural: only one relevant point, or many detours/restarts padding "
        "length to fake rigor.\n"
        "1 Prestructural: irrelevant, self-contradictory, or a corrupted output.\n"
        "\n"
        "DECISION RULE (comparative judgement; Thurstone/ACJ):\n"
        "- Correctness dominates structure: a sound short chain beats a long but wrong one.\n"
        "- Between two chains of comparable reliability, prefer the higher SOLO level; "
        "Warrant and Rebuttal matter most for completeness.\n"
        "- A chain scoring 1 on D1 cannot be preferred over any chain scoring 2 or above "
        "on D1.\n"
        "- Length and confidence are NOT correctness.\n"
    )
    if four_dim:
        pairwise_rubric = rubric_4dim
    elif theory_rubric:
        pairwise_rubric = rubric_toulmin_solo
    reference_line = (
        "No reference answer is provided. Evaluate the two responses on their own merits."
    )

    input_token_count = 0
    output_token_count = 0
    n = len(models)

    for ai in range(n):
        for bi in range(ai + 1, n):
            key_a, key_b = models[ai], models[bi]
            name_a, name_b = model_name_idx[key_a], model_name_idx[key_b]
            resp_a, resp_b = initial_responses[key_a], initial_responses[key_b]
            pair_result = None
            retry_count = 0

            while pair_result is None and retry_count < max_retries:
                prompt_content = (
                    "###Task Description:\n"
                    "An instruction (might include an Input inside it), two responses to "
                    "evaluate (denoted as Response A and Response B), and an evaluation "
                    "criteria are given.\n"
                    "1. Write a detailed feedback that assesses the quality of the two "
                    "responses strictly based on the given evaluation criteria, not "
                    "evaluating in general.\n"
                    + ("1b. Score Response A and Response B on each of the four dimensions "
                       "D1-D4 (1-5), writing the per-dimension scores explicitly in your "
                       "feedback.\n" if four_dim else "")
                    + ("1b. In your feedback, state each chain's SOLO level (1-5) and the "
                       "most important missing Toulmin element (Claim/Data/Warrant/Backing/"
                       "Qualifier/Rebuttal).\n" if theory_rubric else "")
                    + "2. Make comparisons between Response A and Response B. Go straight "
                    "to the point and mention the commonalities and differences between them.\n"
                    "3. After writing the feedback, indicate the better response: \"A\", "
                    "\"B\", or \"tie\" if they are of comparable quality.\n"
                    "4. Also indicate the strength of your preference: \"clearly better\", "
                    "\"better\", \"slightly better\", or \"comparable\".\n"
                    "5. The output format should look as follows: \"Feedback: (write a "
                    "feedback for criteria) [RESULT] (A, B, or tie) [PREFERENCE] (clearly "
                    "better, better, slightly better, or comparable)\"\n"
                    "6. Please do not generate any other opening, closing, and explanations.\n\n"
                    "###Instruction:\n"
                    f"{messages[0]}\n\n"
                    "###Response A:\n"
                    f"{resp_a}\n\n"
                    "###Response B:\n"
                    f"{resp_b}\n\n"
                    "###Reference Answer:\n"
                    f"{reference_line}\n\n"
                    "###Score Rubric:\n"
                    f"{pairwise_rubric}\n\n"
                    "###Feedback:\n"
                )
                prompt = [{"role": "user", "content": prompt_content}]

                try:
                    if judge_model_id == "deepseek":
                        judge_output = _call_deepseek(
                            prompt_content,
                            os.environ.get("DEEPSEEK_API_KEY", ""),
                            model="deepseek-chat",
                            max_tokens=max(max_tokens, 800),
                            retries=max_retries,
                        )
                    else:
                        judge_output, _, _, i_t_c, o_t_c = generate_vllm(
                            model=judge_model_id,
                            endpoint=judge_url,
                            messages=prompt,
                            max_tokens=max_tokens,
                            temperature=0.2,
                            debug_txt=f"[Margin Judge - {name_a} vs {name_b}]",
                            seed=seed
                        )
                        input_token_count += i_t_c
                        output_token_count += o_t_c
                    pair_result, win_margin = _parse_pairwise_margin(judge_output)
                    if pair_result is not None:
                        break
                    print(f"[Margin Judge - {name_a} vs {name_b}] Invalid result: {judge_output[:200]}")
                except Exception as e:
                    print(f"[Margin Judge - {name_a} vs {name_b}] Error: {e}")

                retry_count += 1
                print(f"[Margin Judge - {name_a} vs {name_b}] Retrying ({retry_count}/{max_retries})...")

            if pair_result is None:
                print(f"[Margin Judge - {name_a} vs {name_b}] Max retries reached. Using tie.")
                pair_result, win_margin = "tie", 0.5
                fallback_used[key_a] = True
                fallback_used[key_b] = True

            if pair_result == "A":
                total_scores[key_a] += win_margin
                total_scores[key_b] += 1.0 - win_margin
                score_matrix[ai, bi] = win_margin
                score_matrix[bi, ai] = 1.0 - win_margin
            elif pair_result == "B":
                total_scores[key_b] += win_margin
                total_scores[key_a] += 1.0 - win_margin
                score_matrix[ai, bi] = 1.0 - win_margin
                score_matrix[bi, ai] = win_margin
            else:  # tie
                total_scores[key_a] += 0.5
                total_scores[key_b] += 0.5
                score_matrix[ai, bi] = 0.5
                score_matrix[bi, ai] = 0.5

            judge_count[key_a] += 1
            judge_count[key_b] += 1
            print(f"[Margin Judge - {name_a} vs {name_b}] result={pair_result} margin={win_margin} | "
                  f"{name_a}:{total_scores[key_a]:.2f} {name_b}:{total_scores[key_b]:.2f}")

    return input_token_count, output_token_count, total_scores, judge_count, fallback_used


def _extract_option(text):
    """Heuristic: extract the final answer option letter (A-D) from a model response."""
    if not text:
        return None
    hits = []
    hits += re.findall(r'[\(\[]\s*([A-Da-d])\s*[\)\]]', text)
    hits += re.findall(r'answer\s*(?:is|:)\s*[\(\[\{]?\s*"?\s*([A-Da-d])', text, re.IGNORECASE)
    hits += re.findall(r'"\s*([A-Da-d])\s*"', text)
    return hits[-1].upper() if hits else None


def _vote_pooling(final_response_dict, weights, num_choice=4):
    """Measure 7: trust-weighted voting pooling (DySCo Eq.10 style).
    Returns the answer letter with the highest weighted vote, or None."""
    tally = {}
    for node, resp in final_response_dict.items():
        opt = _extract_option(resp)
        if opt is None:
            continue
        w = weights.get(node, 0.0) if weights else 1.0
        tally[opt] = tally.get(opt, 0.0) + w
    if not tally:
        return None
    return max(tally, key=lambda k: (tally[k], k))


_PRIOR_CACHE = {}


def _norm_q_stem(text):
    import re as _re
    s = (text or "").lower()
    s = _re.sub(r"^question\s*[:：]\s*", "", s)
    s = _re.split(r"\n\s*the options are:", s)[0]
    return _re.sub(r"\s+", " ", s).strip()


def _load_json_cached(path):
    import json
    if path not in _PRIOR_CACHE:
        with open(path, encoding="utf-8") as f:
            _PRIOR_CACHE[path] = json.load(f)
    return _PRIOR_CACHE[path]


def _question_primary_dim(messages, dim_map_path):
    if not dim_map_path:
        return "D2"
    dim_map = _load_json_cached(dim_map_path)
    stem = _norm_q_stem(messages[0] if messages else "")
    return dim_map.get(stem, "D2")


def edge_sampling(models_dict, model_name_idx, initial_responses, messages, temperature=0.7, max_tokens=512, max_retries=3, threshold=0.1, round=None, seed=0, confidences=None, reference_answer=None, edge_mode="judge_absolute", divergence_edges=False, divergence_gamma=0.5, divergence_topk=2, judge_model=None, prior_w1=0.1, profile_path=None, dim_map_path=None):
    """
    Generate edges (relationships) between sampled models and assign scores summing to 1.0.
    edge_mode="judge_absolute": a trusted third-party judge (Prometheus) scores every
        response against a 1-5 rubric (original judge variant, no gold).
    edge_mode="pairwise_copeland": the judge compares responses pairwise (win=1.0,
        tie=0.5 each, loss=0.0), then scores are aggregated and normalized exactly
        as in the original pipeline.
    edge_mode="pairwise_margin": the judge compares responses pairwise and reports
        the strength of preference (clearly/better/slightly), converted to winner
        margins; each node's score is its average margin.
    divergence_edges=True (DySCo-style, measure 5): each receiver keeps its top-k
        sources by edge value s_ij = score_j * (1 + gamma * I[answer_i != answer_j]),
        so dissenting sources get more influence. Per-target weights are normalized.
    """

    try:
        models = list(initial_responses.keys())
        total_scores = {model: 0.0 for model in models}
        n_models = len(models)

        # Initialize score matrix (n_models x n_models) with -1 on diagonal
        score_matrix = np.full((n_models, n_models), np.nan)
        np.fill_diagonal(score_matrix, -1)

        # Track which models used fallback scores
        fallback_used = {model: False for model in models}
        judge_count = {model: 0 for model in models}

        # ============ JUDGE-BASED EDGE SAMPLING ============
        # Trusted third-party evaluator (Prometheus by default; swap via judge_model).
        from endpoint import model_endpoint_dict as _endpoint_dict
        judge_key = judge_model if (judge_model and judge_model in _endpoint_dict) else "prometheus"
        judge_cfg = _endpoint_dict[judge_key]
        judge_model_id = judge_cfg["model_id"]
        judge_url = judge_cfg["url"]

        # External-API judge: keep the raw tag so the score function can route to
        # DeepSeek (absolute 4-dim scores and pairwise-margin variants).
        if judge_model == "deepseek" and edge_mode in (
            "judge_4dim_scores",
            "pairwise_margin", "pairwise_margin_prior",
            "pairwise_margin_4dim", "pairwise_margin_theory",
        ):
            judge_model_id = "deepseek"
            judge_url = ""

        if edge_mode == "pairwise_copeland":
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _pairwise_copeland_scores(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix,
            )
        elif edge_mode == "pairwise_margin":
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _pairwise_margin_scores(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix,
            )
        elif edge_mode == "pairwise_margin_prior":
            # Same pairwise-margin judge; afterwards blend each node's margin score
            # with its ability-profile prior: score = w1*prior + (1-w1)*margin.
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _pairwise_margin_scores(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix,
            )
        elif edge_mode == "pairwise_margin_4dim":
            # Same pipeline as pairwise_margin; only the judge rubric changes to the
            # four ClawTrack-style dimensions. Judge output is longer, so give it
            # more room to finish [RESULT]/[PREFERENCE].
            max_tokens = max(max_tokens, 1600)
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _pairwise_margin_scores(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix, four_dim=True,
            )
        elif edge_mode == "pairwise_margin_theory":
            # Controlled experiment: same pairwise-margin pipeline, judge rubric only
            # replaced by the theory-grounded version (Toulmin + SOLO + Facione).
            max_tokens = max(max_tokens, 1600)
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _pairwise_margin_scores(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix, theory_rubric=True,
            )
        elif edge_mode == "judge_4dim_scores":
            # Explicit four-dimension scores combined by formula; no pairwise winner.
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _judge_4dim_scores(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix,
            )
        elif edge_mode == "judge_absolute_4dim_rubric":
            # Strict control variable: absolute (no-gold) judge with the single generic
            # rubric replaced by the four-dimensional rubric text. Everything else stays.
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _absolute_judge_scores_4dim_rubric(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix,
            )
        elif edge_mode == "judge_absolute_theory_rubric":
            # Strict control variable: absolute (no-gold) judge with the theory-grounded
            # rubric (Toulmin + SOLO + Facione). Everything else stays.
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _absolute_judge_scores_theory_rubric(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix,
            )
        else:
            input_token_count, output_token_count, total_scores, judge_count, fallback_used = _absolute_judge_scores(
                models, model_name_idx, initial_responses, messages,
                judge_model_id, judge_url, temperature, max_tokens, max_retries, seed,
                total_scores, judge_count, fallback_used, score_matrix,
            )
        # ============ END JUDGE-BASED EDGE SAMPLING ============

        # Average scores per model (handles dropped judges fairly)
        avg_scores = {k: (total_scores[k] / judge_count[k] if judge_count[k] > 0 else 0.0) for k in total_scores}

        if edge_mode == "pairwise_margin_prior":
            w1 = float(prior_w1) if prior_w1 is not None else 0.1
            dim = _question_primary_dim(messages, dim_map_path)
            if profile_path:
                profile = _load_json_cached(profile_path)
                for k in avg_scores:
                    pr = profile.get(k, {}).get(dim, 0.25)
                    avg_scores[k] = w1 * pr + (1.0 - w1) * avg_scores[k]
            else:
                print("[Prior] profile_path not provided; skipping prior blend.")

        # Normalize to sum to 1.0
        normalization_factor = 1 / sum(avg_scores.values()) if sum(avg_scores.values()) > 0 else 1.0
        final_scores = {k: v * normalization_factor for k, v in avg_scores.items()}

        # Check if any model used fallback scoring
        edge_sampling_fallback_global = any(fallback_used.values())

        # Sort final ranking
        ranked_scores_dict = dict(sorted(final_scores.items(), key=lambda item: float(item[1]), reverse=True))
        models = list(ranked_scores_dict.keys())
        scores = list(ranked_scores_dict.values())

        edges = []
        total_num_edges = len(models) * (len(models)-1)

        filtered_idx = np.array(scores) > threshold
        models = np.array(models)[filtered_idx]
        scores = np.array(scores)[filtered_idx]
        score_dict = dict(zip(models, scores))

        if len(models) <= 1:
            if len(models) == 1:
                return initial_responses[models[0]]
            else:
                return -1

        # Build edges from ranked models (baseline: high->low complete)
        target_weights = None
        if divergence_edges:
            # DySCo-style divergence-aware edge selection:
            # each receiver keeps its top-k sources by edge value
            # s_ij = score_j * (1 + gamma * I[answer_i != answer_j])
            k = divergence_topk if (divergence_topk is not None and divergence_topk > 0) else len(models) - 1
            answers = {m: _extract_option(initial_responses[m]) for m in models}
            source_edges = {}
            target_edges = {}
            target_weights = {}
            for target in models:
                cands = []
                for source in models:
                    if source == target:
                        continue
                    div = 0.0
                    if answers.get(source) and answers.get(target) and answers[source] != answers[target]:
                        div = 1.0
                    val = float(score_dict[source]) * (1.0 + divergence_gamma * div)
                    cands.append((val, source))
                cands.sort(key=lambda x: -x[0])
                cands = cands[:k]
                total_val = sum(v for v, _ in cands) or 1.0
                target_weights[target] = {s: v / total_val for v, s in cands}
                for v, s in cands:
                    if target not in target_edges:
                        target_edges[target] = []
                    target_edges[target].append(s)
                    if s not in source_edges:
                        source_edges[s] = []
                    source_edges[s].append(target)
            n_edges = sum(len(v) for v in target_edges.values())
            print(f'# of Edges: {n_edges} directed (divergence-aware, topk={k}) / {total_num_edges}')
        else:
            for s_idx in range(len(models) - 1):
                source_node = models[s_idx]
                for target_node in models[s_idx+1:]:
                    edges.append((source_node, target_node))

            print(f'# of Edges: {len(edges)*2} / {total_num_edges}, \t Pruned: {((total_num_edges - len(edges)*2) * 100 / total_num_edges):.2f}%')

            # Initialize edge dictionaries
            source_edges = {}
            target_edges = {}

            for (source, target) in edges:
                if target not in target_edges:
                    target_edges[target] = []
                target_edges[target].append(source)

                if source not in source_edges:
                    source_edges[source] = []
                source_edges[source].append(target)

        return source_edges, target_edges, score_dict, score_matrix, fallback_used, edge_sampling_fallback_global, input_token_count, output_token_count, target_weights

    except Exception as e:
        print(f'Error: {e}')


def _build_reference_descriptions(sources_or_targets, weights, initial_responses):
    """
    Build reference descriptions for message passing.
    Annotates each response with a relevance label (high / moderate / low)
    derived from normalized edge scores.
    """
    descriptions = []
    for ref, weight in zip(sources_or_targets, weights):
        if weight > 0.7:
            desc = f"Model {ref} (high relevance):"
        elif weight > 0.4:
            desc = f"Model {ref} (moderate relevance):"
        else:
            desc = f"Model {ref} (low relevance):"
        descriptions.append(f"{desc}\n{initial_responses[ref]}")
    return "\n\n".join(descriptions)


def _run_s_to_t(model_endpoint_dict, model_name_idx, initial_responses, target_edges, score_dict,
                final_response_dict, messages, temperature, max_tokens,
                round, final_prompt, seed, target_weights=None, anti_sycophancy=False):
    """Source -> Target: each target refines its response using source models' responses."""
    input_token_total = 0
    output_token_total = 0

    sorted_targets = sorted(target_edges.keys())
    for target in sorted_targets:

        sources = target_edges[target]
        if target_weights is not None and target in target_weights:
            tw = target_weights[target]
            source_weights = [tw[s] for s in sources]
        else:
            source_scores = [score_dict[source] for source in sources]
            total_score = sum(source_scores)
            source_weights = [s / total_score for s in source_scores]

        descriptions = _build_reference_descriptions(sources, source_weights, initial_responses)

        # --- SIMPLIFIED PROMPT: single user message ---
        prompt_content = (
            f"Refine your answer by considering other models' responses.\n\n"
            f"Question: {messages[0]}\n\n"
            f"Your initial response: {initial_responses[target]}\n\n"
            f"Other models' responses (ranked by relevance):\n{descriptions}\n\n"
            f"Integrate useful insights from these responses to improve your answer. "
            f"Be critical — some information may be incorrect.\n"
        )
        if anti_sycophancy:
            prompt_content += (
                f"Do not automatically follow the majority opinion. "
                f"Revise your answer ONLY if the feedback exposes a real reasoning error, "
                f"missing evidence, or a stronger alternative. "
                f"If you keep your original answer, briefly explain why the feedback is insufficient. "
                f"If you revise, state which model's feedback was most useful.\n"
            )

        prompt = [{"role": "user", "content": prompt_content}]

        target_model_name = model_name_idx[target]
        model = model_endpoint_dict[target_model_name]['model_id']
        endpoint = model_endpoint_dict[target_model_name]['url']

        refined_target_response, _, _, input_token_count, output_token_count = generate_vllm(
            model=model,
            endpoint=endpoint,
            messages=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            debug_txt=f"[Round {round}] [(S -> T): Refining Target] ",
            seed=seed
        )

        input_token_total += input_token_count
        output_token_total += output_token_count

        final_response_dict[target] = refined_target_response

    return final_response_dict, input_token_total, output_token_total


def _run_t_to_s(model_endpoint_dict, model_name_idx, initial_responses, source_edges, score_dict,
                final_response_dict, source_with_most_edges, messages, temperature, max_tokens,
                round, final_prompt, seed, target_weights=None, anti_sycophancy=False):
    """Target -> Source: each source refines its response using target models' refined responses."""
    input_token_total = 0
    output_token_total = 0
    final_user_prompt = final_prompt if source_with_most_edges else ''

    sorted_sources = sorted(source_edges.keys())

    for source in sorted_sources:
        if source_with_most_edges and source != source_with_most_edges:
            continue

        targets = source_edges[source]
        if target_weights is not None and source in target_weights:
            tw = target_weights[source]
            tgt_w = [tw[t] for t in targets]
        else:
            target_scores = [score_dict[t] for t in targets]
            total_score = sum(target_scores)
            tgt_w = [t / total_score for t in target_scores]

        descriptions = _build_reference_descriptions(targets, tgt_w, final_response_dict)

        # --- SIMPLIFIED PROMPT: single user message ---
        prompt_content = (
            f"Other models refined their answers after seeing yours. Use their improvements to finalize your response.\n\n"
            f"Question: {messages[0]}\n\n"
            f"Your initial response: {initial_responses[source]}\n\n"
            f"Updated responses from other models:\n{descriptions}\n\n"
            f"Write your final response, incorporating valuable refinements. "
            f"Be critical — some information may be incorrect.\n"
            f"{final_user_prompt}"
        )
        if anti_sycophancy:
            prompt_content += (
                f"Do not automatically follow the majority opinion. "
                f"Finalize your answer based on your own reasoning. "
                f"Revise ONLY if the feedback exposes a real reasoning error, missing evidence, "
                f"or a stronger alternative. "
                f"If you keep your original answer, briefly explain why the feedback is insufficient. "
                f"If you revise, state which model's feedback was most useful.\n"
            )

        prompt = [{"role": "user", "content": prompt_content}]

        source_model_name = model_name_idx[source]
        model = model_endpoint_dict[source_model_name]['model_id']
        endpoint = model_endpoint_dict[source_model_name]['url']

        refined_source_response, _, _, input_token_count, output_token_count = generate_vllm(
            model=model,
            endpoint=endpoint,
            messages=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            debug_txt=f"[Round {round}] [(T -> S): Updating Source] ",
            seed=seed
        )

        input_token_total += input_token_count
        output_token_total += output_token_count

        final_response_dict[source] = refined_source_response

    return final_response_dict, input_token_total, output_token_total


def message_passing(model_endpoint_dict, model_name_idx, initial_responses, source_edges, target_edges, score_dict,
                     source_with_most_edges=None, messages=None,
                     temperature=0.7, max_tokens=512, round=None, final_prompt='', seed=0,
                     target_weights=None, anti_sycophancy=False):
    """
    Pass messages between nodes (models) to iteratively improve responses.
    Bidirectional: S->T then T->S.
    """
    final_response_dict = {}
    input_token_total = 0
    output_token_total = 0

    try:
        # Step 1: S -> T
        final_response_dict, i_t_c, o_t_c = _run_s_to_t(
            model_endpoint_dict, model_name_idx, initial_responses, target_edges, score_dict,
            final_response_dict, messages, temperature, max_tokens,
            round, final_prompt, seed, target_weights=target_weights, anti_sycophancy=anti_sycophancy)
        input_token_total += i_t_c
        output_token_total += o_t_c

        after_phase1 = deepcopy(final_response_dict)

        # Step 2: T -> S
        final_response_dict, i_t_c, o_t_c = _run_t_to_s(
            model_endpoint_dict, model_name_idx, initial_responses, source_edges, score_dict,
            final_response_dict, source_with_most_edges, messages, temperature, max_tokens,
            round, final_prompt, seed, target_weights=target_weights, anti_sycophancy=anti_sycophancy)
        input_token_total += i_t_c
        output_token_total += o_t_c

        return after_phase1, final_response_dict, input_token_total, output_token_total

    except Exception as e:
        print(f"Error in message passing: {e}")



def graph_pooling(model, endpoint, refined_response, messages, weights=None, temperature=0.7, max_tokens=512, final_prompt='', seed=0):
    """
    Aggregate responses from all nodes into a single final response.
    """

    try:
        response_parts = []
        if weights:
            for node, response in refined_response.items():
                weight = weights[node]
                if weight > 0.7:
                    header = f"Model {node} (high relevance):"
                elif weight > 0.4:
                    header = f"Model {node} (moderate relevance):"
                else:
                    header = f"Model {node} (low relevance):"
                response_parts.append(f"{header}\n{response}")
            debug_txt = "[Graph Pooling - Weighted Mean] "
        else:
            for node, response in refined_response.items():
                response_parts.append(f"Model {node}:\n{response}")
            debug_txt = "[Graph Pooling - Mean] "

        input_responses = "\n\n".join(response_parts)

        # --- SIMPLIFIED PROMPT: single user message ---
        prompt_content = (
            f"Synthesize these model responses into one final answer.\n\n"
            f"Question: {messages[0]}\n\n"
            f"Model responses:\n{input_responses}\n\n"
            f"Produce an accurate, coherent answer integrating the best insights. "
            f"Be critical — some information may be incorrect.\n"
            f"{final_prompt}"
        )

        prompt = [{"role": "user", "content": prompt_content}]

        final_response, _, _, input_token_count, output_token_count = generate_vllm(
            model=model,
            endpoint=endpoint,
            messages=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            debug_txt=debug_txt,
            seed=seed
        )

        return final_response, input_token_count, output_token_count

    except Exception as e:
        print(f'Error: {e}')
