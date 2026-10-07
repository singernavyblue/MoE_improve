#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""能力画像拟合：按 Q 矩阵分维度估计每模型每维能力（纯 numpy）。

指标设计（6 个模型的小样本场景）：
  - accuracy：每维正确率（主指标，稳定，含二项标准误）
  - std_resid：难度校正残差得分（次指标）
  - theta_2pl：2PL 联合估计（仅当模型数 >= 20 时启用；
               6 个被试下联合估计不可靠，输出 null 并给出警告）

输入：
  作答矩阵 JSON: {model: {record_id: 1/0}}（1=答对）
  Q 矩阵 JSON:   {record_id: [d1,d2,d3,d4]}（1=该题考该维）
输出：
  画像卡 JSON: 每模型 {theta, mastery, se, n_items, item_params}

用法：
  python fit_irt.py --answers answers.json --qmatrix qmatrix.json --out profiles.json
"""

import argparse
import json
import numpy as np


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _logistic(z):
    return 1.0 / (1.0 + np.exp(-z))


def fit_2pl_dim(X, ridge=0.5, steps=200, step_size=0.4):
    """对单个维度的作答矩阵 X (M×J, 0/1) 做 2PL 联合估计。
    交替更新：题目参数 (a,b) → 模型能力 θ，均为带岭正则的牛顿步。
    返回 theta(M), a(J), b(J), se(M)。
    """
    M, J = X.shape
    pj = X.mean(axis=0)
    b = -_logit(pj)
    a = np.ones(J)
    theta = _logit(X.mean(axis=1))

    for _ in range(steps):
        # 1) 更新题目参数
        for j in range(J):
            z = a[j] * (theta - b[j])
            p = _logistic(z)
            w = p * (1 - p)
            tmb = theta - b[j]
            h11 = float((w * tmb ** 2).sum()) + ridge
            h12 = float(-(w * a[j] * tmb).sum())
            h22 = float((w * a[j] ** 2).sum()) + ridge
            det = h11 * h22 - h12 ** 2
            if abs(det) < 1e-12:
                continue
            g_a = float((X[:, j] * tmb).sum() - (p * tmb).sum()) - ridge * a[j]
            g_b = float((-X[:, j] * a[j]).sum() + (p * a[j]).sum()) - ridge * b[j]
            da = (h22 * g_a - h12 * g_b) / det
            db = (-h12 * g_a + h11 * g_b) / det
            a[j] += step_size * da
            b[j] += step_size * db
        # 2) 更新模型能力
        for m in range(M):
            z = a * (theta[m] - b)
            p = _logistic(z)
            w = p * (1 - p)
            h = float((w * a ** 2).sum()) + ridge
            g = float((X[m] * a).sum() - (p * a).sum()) - ridge * theta[m]
            theta[m] += step_size * g / h
        # 固定识别：θ 每轮标准化（均值 0、方差 1）
        theta = (theta - theta.mean()) / (theta.std() + 1e-9)

    # 标准误：Fisher 信息开方倒数
    se = []
    for m in range(M):
        z = a * (theta[m] - b)
        info = float((_logistic(z) * (1 - _logistic(z)) * a ** 2).sum())
        se.append(1.0 / np.sqrt(info) if info > 0 else np.nan)
    return theta, a, b, np.array(se)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--qmatrix", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul")
    args = ap.parse_args()

    answers = json.load(open(args.answers, encoding="utf-8"))  # {model: {record_id: 0/1}}
    qm = json.load(open(args.qmatrix, encoding="utf-8"))       # {record_id: [d1,d2,d3,d4]}
    models = [m for m in args.models.split(",") if m in answers]
    dims = ["D1", "D2", "D3", "D4"]

    profiles = {m: {"accuracy": {}, "std_resid": {}, "theta_2pl": {}, "mastery": {}, "se": {}, "n_items": {}} for m in models}
    item_params = {}
    M = len(models)

    for di, dim in enumerate(dims):
        items = [rid for rid, q in qm.items() if q[di] == 1]
        if not items:
            item_params[dim] = {"a": [], "b": []}
            for m in models:
                profiles[m]["accuracy"][dim] = 0.5
                profiles[m]["std_resid"][dim] = 0.0
                profiles[m]["theta_2pl"][dim] = None
                profiles[m]["mastery"][dim] = 0.5
                profiles[m]["se"][dim] = None
                profiles[m]["n_items"][dim] = 0
            continue
        X = np.array([[answers[m].get(rid, 0) for rid in items] for m in models], dtype=float)
        acc = X.mean(axis=1)
        pj = X.mean(axis=0).clip(1e-3, 1 - 1e-3)
        std_resid = ((X - pj) / np.sqrt(pj * (1 - pj))).mean(axis=1)
        se = np.sqrt(acc * (1 - acc) / len(items))
        theta2 = None
        if M >= 20:
            theta, a, b, se2 = fit_2pl_dim(X)
            theta2 = theta.tolist()
            item_params[dim] = {"record_ids": items, "a": a.tolist(), "b": b.tolist()}
        else:
            item_params[dim] = {"record_ids": items, "note": "M<20：2PL 联合估计不可靠，未启用"}
        for mi, m in enumerate(models):
            profiles[m]["accuracy"][dim] = float(acc[mi])
            profiles[m]["std_resid"][dim] = float(std_resid[mi])
            profiles[m]["theta_2pl"][dim] = theta2[mi] if theta2 is not None else None
            profiles[m]["mastery"][dim] = float(acc[mi])
            profiles[m]["se"][dim] = float(se[mi])
            profiles[m]["n_items"][dim] = len(items)

    if M < 20:
        print(f"[提示] 模型数 M={M} < 20：2PL θ 联合估计不可靠，画像采用每维正确率（accuracy）与难度校正残差（std_resid），θ 置 null。")

    out = {
        "dims": dims,
        "models": {m: profiles[m] for m in models},
        "item_params": item_params,
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved:", args.out)
    for m in models:
        acc = profiles[m]["accuracy"]
        print(f"{m}: " + " ".join(f"{d}={acc[d]:.3f}" for d in dims))


if __name__ == "__main__":
    main()
