# Tools image for one-off ECS tasks on AWS (db init: restore + CDC; bulk load SQL Server -> DynamoDB; reset demo;
# C2-7 synthetic-load / synthetic-trickle: generated rows into SQL Server, carried on by CDC).
# Build context: repository root.
FROM public.ecr.aws/docker/library/python:3.12-slim
RUN pip install --no-cache-dir "boto3==1.*" "pymssql==2.*" "pyyaml==6.*" "numpy==2.*" "holidays==0.*" && useradd -m -u 1654 tools
WORKDIR /repo
COPY design/mapping/ design/mapping/
COPY scripts/loader/ scripts/loader/
COPY scripts/synthetic/ scripts/synthetic/
COPY scripts/aws/ scripts/aws/
COPY scripts/reset-demo.sql scripts/
COPY cdc/awcdc/ cdc/awcdc/
USER 1654
ENTRYPOINT ["bash", "scripts/aws/tools-entrypoint.sh"]
