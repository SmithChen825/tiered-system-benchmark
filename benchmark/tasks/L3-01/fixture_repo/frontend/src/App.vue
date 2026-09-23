<script setup>
import { onMounted, ref } from "vue";


const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const account = ref(null);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    const response = await fetch(`${apiBaseUrl}/api/account`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Account request failed with HTTP ${response.status}`);
    }
    account.value = await response.json();
  } catch (requestError) {
    error.value = "Unable to load account data.";
    console.error(requestError);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main class="account-shell">
    <p class="eyebrow">Northstar Workspace</p>
    <h1>Account</h1>
    <section class="account-panel" aria-live="polite">
      <p v-if="loading" data-testid="loading">Loading account…</p>
      <p v-else-if="error" class="error" data-testid="error">{{ error }}</p>
      <dl v-else-if="account" data-testid="account-card">
        <div>
          <dt>Name</dt>
          <dd data-testid="account-name">{{ account.name }}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd data-testid="account-role">{{ account.role }}</dd>
        </div>
        <div>
          <dt>Plan</dt>
          <dd>{{ account.plan }}</dd>
        </div>
      </dl>
    </section>
  </main>
</template>
