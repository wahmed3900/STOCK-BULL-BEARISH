{% if user.subscription == "pro" %}
  {% include "components/sentiment_timeline.html" %}
{% else %}
  <p class="text-slate-400">Upgrade to Pro to unlock the Sentiment Timeline</p>
{% endif %}
