# Quant Lab strategy sandbox: a throwaway container per run with no network, a read-only root filesystem, no
# capabilities and an unprivileged user. Built by api/quant/sandbox.py (ensure_image) — the same library versions as
# the platform, so a strategy computes the same numbers in the browser, the container and the fallback sandbox.
FROM python:3.12-slim

ARG NUMPY=1.26.4
ARG PANDAS=3.0.2
ARG SCIPY=1.17.1
ARG SKLEARN=1.8.0
ARG STATSMODELS=0.14.6

RUN pip install --no-cache-dir "numpy==${NUMPY}" "pandas==${PANDAS}" "scipy==${SCIPY}" \
        "scikit-learn==${SKLEARN}" "statsmodels==${STATSMODELS}" \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin strategy \
    && mkdir /engine /work && chown strategy /work

ENV PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLCONFIGDIR=/tmp
USER strategy
WORKDIR /work
