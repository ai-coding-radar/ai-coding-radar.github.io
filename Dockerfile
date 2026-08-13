FROM apify/actor-python:3.13

USER myuser
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=myuser:myuser apify_actor ./apify_actor
RUN python -m compileall -q apify_actor/
CMD ["python", "-m", "apify_actor"]
