FROM python:3.12-slim
WORKDIR /app

# The app runs as its own unprivileged user rather than as root, so a process that
# answers the public internet owns nothing it does not need. The uid and gid are
# fixed so that a volume's ownership means the same thing from one build to the next.
RUN groupadd --gid 10001 --system appuser \
    && useradd --uid 10001 --gid 10001 --system --create-home \
       --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
COPY entrypoint.sh fix-volumes.sh ./
# Only the two places the app writes are its own; the code stays root's, so the
# app cannot rewrite itself. A named volume mounted over an empty path takes that
# path's ownership from the image, which is how a fresh install's volumes come to
# belong to appuser. An install from before this has volumes that are still root's;
# the api-init service in docker-compose.yml puts those right (fix-volumes.sh).
RUN chmod +x entrypoint.sh fix-volumes.sh \
    && mkdir -p /app/images /app/files /app/stats \
    && chown appuser:appuser /app/images /app/files

USER appuser
EXPOSE 8000
CMD ["./entrypoint.sh"]
