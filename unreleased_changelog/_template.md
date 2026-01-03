{% for section, _ in sections.items() %}
{% if section %}## {{ section }}{% endif %}
{% if sections[section] %}
{% for category, val in definitions.items() if category in sections[section] %}

### {{ definitions[category]['name'] }}

{% for fragment in sections[section][category] %}
- {{ fragment }}
{% endfor %}
{% endfor %}

{% endif %}
{% endfor %}
