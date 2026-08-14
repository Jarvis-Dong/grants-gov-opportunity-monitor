FROM apify/actor-python:3.13

USER myuser
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=myuser:myuser grants_gov_opportunity_monitor ./grants_gov_opportunity_monitor
COPY --chown=myuser:myuser .actor ./.actor
RUN python -m compileall -q grants_gov_opportunity_monitor

CMD ["python", "-m", "grants_gov_opportunity_monitor.main"]
