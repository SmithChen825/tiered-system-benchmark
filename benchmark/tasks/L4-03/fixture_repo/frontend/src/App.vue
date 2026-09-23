<script setup>
import { onMounted, ref } from "vue";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const dashboard = ref(null);
const error = ref("");

async function loadDashboard() {
  error.value = "";
  try {
    const response = await fetch(`${apiBaseUrl}/api/dashboard`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    dashboard.value = await response.json();
  } catch (requestError) {
    error.value = "Dashboard unavailable.";
    console.error(requestError);
  }
}

onMounted(loadDashboard);
</script>

<template>
  <main class="dashboard-shell">
    <p class="eyebrow">Northstar operations</p>
    <h1>System dashboard</h1>
    <p v-if="error" class="error" data-testid="dashboard-error" role="alert">{{ error }}</p>
    <section v-else-if="dashboard" data-testid="dashboard">
      <div class="summary">
        <div><span>System</span><strong data-testid="system-status">{{ dashboard.status }}</strong></div>
        <div><span>Database</span><strong data-testid="database-status">{{ dashboard.database }}</strong></div>
      </div>
      <div class="metrics">
        <article v-for="metric in dashboard.metrics" :key="metric.name" data-testid="metric-card">
          <span>{{ metric.name }}</span><strong>{{ metric.value }}</strong>
        </article>
      </div>
    </section>
    <p v-else data-testid="dashboard-loading">Checking services…</p>
  </main>
</template>

