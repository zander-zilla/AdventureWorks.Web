# Tools image for one-off ECS tasks on AWS (db init: restore + CDC; bulk load SQL Server -> DynamoDB; reset demo).
# Build context: repository root.
FROM public.ecr.aws/docker/library/python:3.12-slim
RUN pip install --no-cache-dir "boto3==1.*" "pymssql==2.*" "pyyaml==6.*" && useradd -m -u 1654 tools
WORKDIR /repo
COPY design/mapping/ design/mapping/
COPY scripts/loader/ scripts/loader/
COPY scripts/aws/ scripts/aws/
COPY scripts/reset-demo.sql scripts/
COPY cdc/awcdc/ cdc/awcdc/
USER 1654
ENTRYPOINT ["bash", "scripts/aws/tools-entrypoint.sh"]
