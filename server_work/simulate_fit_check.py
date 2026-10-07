#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用模拟数据验证 fit_irt 的 2PL 拟合器：能否恢复已知的模型能力 θ。"""

import json
import numpy as np
from fit_irt import fit_2pl_dim, _logistic

rng = np.random.default_rng(0)
M, J = 6, 35
theta_true = rng.normal(0, 1, M)
a_true = np.exp(rng.normal(0, 0.3, J))
b_true = rng.normal(0, 1, J)
p = _logistic(a_true[None, :] * (theta_true[:, None] - b_true[None, :]))
X = (rng.random((M, J)) < p).astype(float)

theta_fit, a_fit, b_fit, se = fit_2pl_dim(X)
corr = np.corrcoef(theta_true, theta_fit)[0, 1]
print("theta_true:", np.round(theta_true, 2))
print("theta_fit :", np.round(theta_fit, 2))
print("corr(theta_true, theta_fit) =", round(corr, 3))
print("SE:", np.round(se, 3))
print("通过标准：|corr| >= 0.7 ->", "PASS" if corr >= 0.7 else "FAIL")

# 保存一份模拟作答矩阵与 Q 矩阵，供 fit_irt.py 端到端演示
models = ["qwen", "qwen_coder", "mathstral", "biomedical_llama", "finance_llama", "saul"]
ids = [f"sim_{i:03d}" for i in range(J)]
answers = {m: {ids[j]: int(X[i, j]) for j in range(J)} for i, m in enumerate(models)}
qmatrix = {rid: [1 if j % 4 == 0 else 0, 1 if j % 4 == 1 else 0, 1 if j % 4 == 2 else 0, 1 if j % 4 == 3 else 0] for j, rid in enumerate(ids)}
json.dump(answers, open("/tmp/sim_answers.json", "w"), ensure_ascii=False)
json.dump(qmatrix, open("/tmp/sim_qmatrix.json", "w"), ensure_ascii=False)
print("sim files saved to /tmp")
