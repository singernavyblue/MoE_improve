p = '/root/GoA/utils.py'
src = open(p).read()
assert 'FULL_RESPONSE' not in src, 'already patched?'

n_prompt = src.count('                res = requests.post(')
src = src.replace(
    '                res = requests.post(',
    '                logger.debug(f"{debug_txt} FULL_PROMPT: {prompt[:5000]}")\n                res = requests.post('
)

src = src.replace(
    '            answer = output[0]',
    '            answer = output[0]\n            logger.debug(f"{debug_txt} FULL_RESPONSE: {answer[:3000]}")'
)

open(p, 'w').write(src)
print('patched OK, requests.post sites:', n_prompt)
