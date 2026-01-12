# ZenML → TRMNL Private Plugin

Display ZenML pipeline status on a [TRMNL](https://usetrmnl.com) e-ink display, updated automatically via GitHub Actions.

![TRMNL Display](assets/plugin-a3b454.png)

## Features

- **Recent Runs View**: Shows the last 12 pipeline runs with status, duration, and timing
- **Pipelines Overview**: Lists all pipelines with their latest run status
- **Running Only View**: Focus on currently executing pipelines (auto-switches to recent runs when idle)
- **24-hour Statistics**: Running, completed, failed, and cached counts
- **Configurable Timezone**: Display times in your local timezone
- **Dry Run Mode**: Test locally before pushing to your device

## Quick Start

### 1. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and set up the project

```bash
git clone https://github.com/YOUR_USERNAME/trmnl-zenml.git
cd trmnl-zenml
uv sync
```

### 3. Create a ZenML Service Account

```bash
zenml service-account create trmnl-dashboard
# Save the API key that's printed!
```

### 4. Test locally with dry-run

```bash
export ZENML_SERVER_URL="https://your-zenml-server.example.com"
export ZENML_API_KEY="your-api-key"
export ZENML_PROJECT="default"  # Or your project name
export DISPLAY_TIMEZONE="Europe/Berlin"  # Optional

uv run python zenml_trmnl.py --dry-run
```

### 5. Set up TRMNL Private Plugin

1. Go to your [TRMNL dashboard](https://usetrmnl.com)
2. Create a new **Private Plugin**
3. Set the data source to **Webhook**
4. Copy the Webhook URL
5. Paste the [markup template](#trmnl-markup-templates) into the editor
6. Save and add to your playlist

### 6. Push to your device

```bash
export TRMNL_WEBHOOK_URL="https://usetrmnl.com/api/custom_plugins/your-uuid"
uv run python zenml_trmnl.py
```

## GitHub Actions Setup (Automated Updates)

The included workflow updates your TRMNL display every 5 minutes.

### Required Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `ZENML_SERVER_URL` | Your ZenML server URL |
| `ZENML_API_KEY` | ZenML service account API key |
| `ZENML_PROJECT` | ZenML project name (e.g., `default`) |
| `TRMNL_WEBHOOK_URL` | TRMNL webhook URL from your plugin |

### Optional Variables

Go to **Settings → Secrets and variables → Actions → Variables** and add:

| Variable | Default | Description |
|----------|---------|-------------|
| `DISPLAY_TIMEZONE` | `UTC` | Timezone for timestamps (e.g., `Europe/Berlin`) |

### Manual Trigger

You can manually trigger the workflow from the Actions tab with options:
- **View mode**: Choose between `recent_runs`, `pipelines_overview`, or `running_only`
- **Dry run**: Print payload without sending to TRMNL

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ZENML_SERVER_URL` | Yes | - | ZenML server URL |
| `ZENML_API_KEY` | Yes | - | ZenML service account API key |
| `ZENML_PROJECT` | No | `default` | ZenML project name or ID |
| `TRMNL_WEBHOOK_URL` | Yes* | - | TRMNL webhook URL (*not needed for `--dry-run`) |
| `VIEW_MODE` | No | `recent_runs` | View mode: `recent_runs`, `pipelines_overview`, `running_only` |
| `DISPLAY_TIMEZONE` | No | `UTC` | Timezone for display (e.g., `Europe/Berlin`, `America/New_York`) |

## TRMNL Markup Templates

Copy these templates into your TRMNL Private Plugin's markup editor.

> **Design Note**: These templates use TRMNL's native Framework classes for optimal e-ink rendering. No custom styles needed.

### Recent Runs View (Full Screen)

```html
<div class="view">
  <div class="layout layout--col">
    <!-- Stats Header -->
    <div class="flex flex--row flex--center-y gap--medium py--8 border--h-1 mb--8">
      <div class="flex flex--row flex--center-y gap--xsmall">
        <span class="value value--large">{{ running_count }}</span>
        <span class="label label--small">► RUNNING</span>
      </div>
      <span class="divider--v"></span>
      <div class="flex flex--row flex--center-y gap--xsmall">
        <span class="value value--large">{{ completed_count }}</span>
        <span class="label label--small">✓ OK</span>
      </div>
      <span class="divider--v"></span>
      <div class="flex flex--row flex--center-y gap--xsmall">
        <span class="label label--inverted px--4 py--2">{{ failed_count }}</span>
        <span class="label label--small">✗ FAILED</span>
      </div>
      <span class="label label--small text--gray-50 grow text--right">{{ stats_period }}</span>
    </div>

    <!-- Pipeline Runs Table -->
    <table class="table table--small" data-table-limit="true">
      <thead>
        <tr>
          <th></th>
          <th><span class="title title--small">Run</span></th>
          <th><span class="title title--small">Pipeline</span></th>
          <th><span class="title title--small">Started</span></th>
          <th><span class="title title--small text--right">Duration</span></th>
        </tr>
      </thead>
      <tbody>
        {% for run in runs %}
        <tr class="{% if run.is_failed %}bg--gray-20{% elsif run.in_progress %}bg--gray-10{% endif %}">
          <td>
            {% if run.is_failed %}<span class="label label--inverted">{{ run.status_icon }}</span>{% else %}<span class="label">{{ run.status_icon }}</span>{% endif %}
          </td>
          <td><span class="label label--small" data-clamp="1">{{ run.name }}</span></td>
          <td><span class="label label--small text--gray-40" data-clamp="1">{{ run.pipeline }}</span></td>
          <td><span class="label label--small">{{ run.started }}</span></td>
          <td><span class="label label--small text--right">{{ run.duration }}</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="title_bar">
    <img class="image" src="https://zenml.io/favicon.ico" />
    <span class="title">ZenML</span>
    <span class="instance">{{ updated_at }}</span>
  </div>
</div>
```

### Pipelines Overview (Half Vertical)

```html
<div class="view">
  <div class="layout">
    <div class="columns">
      <div class="column">
        <span class="title mb--8">{{ title }}</span>

        <table class="table table--xsmall" data-table-limit="true">
          <thead>
            <tr>
              <th></th>
              <th><span class="title title--small">Pipeline</span></th>
              <th><span class="title title--small">Status</span></th>
            </tr>
          </thead>
          <tbody>
            {% for pipeline in pipelines %}
            <tr class="{% if pipeline.is_failed %}bg--gray-20{% endif %}">
              <td>{% if pipeline.is_failed %}<span class="label label--inverted">{{ pipeline.status_icon }}</span>{% else %}<span class="label">{{ pipeline.status_icon }}</span>{% endif %}</td>
              <td><span class="label label--small" data-clamp="1">{{ pipeline.name }}</span></td>
              <td><span class="label label--small">{{ pipeline.latest_status }}</span></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>

        <span class="label label--small text--gray-50 mt--8">{{ updated_at }}</span>
      </div>
    </div>
  </div>

  <div class="title_bar">
    <span class="title">ZenML Pipelines</span>
  </div>
</div>
```

### Running Only (Quadrant)

```html
<div class="view">
  <div class="layout">
    <div class="columns">
      <div class="column">
        <div class="flex flex--row flex--center-y gap--small mb--8">
          <span class="value value--xlarge">{{ running_count }}</span>
          <span class="label">Running</span>
        </div>

        {% for run in runs limit:3 %}
        <div class="flex flex--row flex--center-y gap--xsmall mb--4">
          <span class="label label--small">►</span>
          <span class="label label--small" data-clamp="1">{{ run.pipeline }}</span>
          <span class="label label--small text--gray-50">{{ run.duration }}</span>
        </div>
        {% endfor %}

        {% if running_count == 0 %}
        <span class="label label--small text--gray-50">No pipelines running</span>
        {% endif %}
      </div>
    </div>
  </div>

  <div class="title_bar">
    <span class="title">ZenML</span>
  </div>
</div>
```

## Publishing Your Plugin

When publishing to the TRMNL Recipe Store, you'll need:

1. **Author Bio** (`author_bio` field) - Required for end-user support. Add this in your plugin's custom fields.
2. **Icon** - Upload a plugin icon in the Settings view.

See [Custom Plugin Form Builder](https://help.usetrmnl.com/en/articles/10513740-custom-plugin-form-builder) for details.

## Status Icons

| Status | Icon |
|--------|------|
| Completed | ✓ |
| Running | ► |
| Failed | ✗ |
| Cached | ≡ |
| Initializing/Provisioning | ○ |
| Stopped | ■ |
| Stopping | □ |
| Retried | ↻ |

## License

MIT
