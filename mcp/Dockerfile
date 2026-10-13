FROM python:3.12-slim
WORKDIR /app

# Its own unprivileged user, as the app has: the server handles what an agent sends
# it and holds the API token, and as root it would own its container outright. The
# uid is fixed, as api's is, so it means the same thing from one build to the next.
# It writes nothing, so nothing here is given to it; the code stays root's.
RUN groupadd --gid 10001 --system appuser \
    && useradd --uid 10001 --gid 10001 --system --no-create-home \
       --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

USER appuser
EXPOSE 8001
CMD ["python", "server.py"]
