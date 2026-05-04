const OWNER = "alonmorad9";
const REPO = "swing-stock-alert";
const WORKFLOW_FILE = "main.yml";

function modeForSchedule(schedule) {
  // Monthly review cron should pass mode=monthly. Everything else is a weekly pilot scan.
  if (schedule && schedule.startsWith("30 21 28-31")) {
    return "monthly";
  }
  return "weekly";
}

function isMonthEnd(scheduledTime) {
  const current = new Date(scheduledTime);
  const tomorrow = new Date(current.getTime() + 24 * 60 * 60 * 1000);
  return tomorrow.getUTCMonth() !== current.getUTCMonth();
}

async function triggerWorkflow(env, schedule = "") {
  const mode = modeForSchedule(schedule);
  console.log("Dispatching GitHub workflow", {
    owner: OWNER,
    repo: REPO,
    workflow: WORKFLOW_FILE,
    schedule,
    mode,
  });

  const response = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "swing-stock-alert-scheduler",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          mode,
          schedule,
        },
      }),
    },
  );

  if (!response.ok) {
    const body = await response.text();
    console.error("GitHub dispatch failed", {
      status: response.status,
      body,
      schedule,
      mode,
    });
    throw new Error(`GitHub dispatch failed: ${response.status} ${body}`);
  }

  console.log("GitHub dispatch succeeded", {
    status: response.status,
    schedule,
    mode,
  });
}

export default {
  async scheduled(event, env, ctx) {
    console.log("Scheduled trigger fired", {
      cron: event.cron,
      scheduledTime: event.scheduledTime,
    });

    if (event.cron.startsWith("30 21 28-31") && !isMonthEnd(event.scheduledTime)) {
      console.log("Skipping monthly comparison because this is not the final calendar day.");
      return;
    }

    ctx.waitUntil(triggerWorkflow(env, event.cron));
  },

  async fetch(request, env) {
    console.log("Manual trigger received", {
      method: request.method,
      url: request.url,
    });

    if (request.method !== "POST") {
      return new Response("Use POST to trigger the swing stock workflow.\n", { status: 405 });
    }

    await triggerWorkflow(env);
    return new Response("Triggered swing stock pilot workflow.\n");
  },
};
