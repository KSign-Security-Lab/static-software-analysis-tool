# SEC-bench's evaluator, pinned.
#
# Their README wants conda and Python 3.12. This puts both in an image instead,
# so nothing is installed on the host and scoring is reproducible -- the same
# commit evaluates the same way next month as today, which matters more here
# than anywhere else in this repo because the number is the product.
#
# Only the evaluator runs from this image. Our agent runs on the host against
# the model already serving there; this container exists to build and test the
# patches our agent produced, using their code rather than a reimplementation
# of it.
FROM python:3.12-slim

# The pin. A tag would drift and a floating main would make last week's number
# unreproducible; update it deliberately and re-run the sweep.
ARG SECBENCH_REF=main

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# The Docker CLI only -- the daemon is the sibling `secbench-docker` service.
# `docker.io` would pull a second daemon we would then have to keep stopped.
COPY --from=docker:28-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /opt
RUN git clone --recurse-submodules https://github.com/SEC-bench/SEC-bench.git \
    && cd SEC-bench \
    && git checkout "${SECBENCH_REF}" \
    && git rev-parse HEAD > /opt/SECBENCH_COMMIT \
    && pip install --no-cache-dir -r requirements.txt

WORKDIR /opt/SEC-bench

# Written by the sweep, read by the evaluator. Bind-mounted, so results survive
# the container and a rebuild costs nothing.
VOLUME ["/secbench"]
ENV SECB_ROOT=/secbench
