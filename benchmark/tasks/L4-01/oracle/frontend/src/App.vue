<script setup>
import { onMounted, ref } from "vue";


const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const users = ref([]);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    const response = await fetch(`${apiBaseUrl}/api/users`);
    if (!response.ok) {
      throw new Error(`Users request failed with HTTP ${response.status}`);
    }
    users.value = await response.json();
  } catch (requestError) {
    error.value = "Unable to load the user directory.";
    console.error(requestError);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main class="directory-shell">
    <p class="eyebrow">Northstar Operations</p>
    <h1>User directory</h1>
    <section class="directory-panel" aria-live="polite">
      <p v-if="loading" data-testid="loading">Loading users…</p>
      <p v-else-if="error" class="error" data-testid="error">{{ error }}</p>
      <table v-else data-testid="user-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id" data-testid="user-row">
            <td>{{ user.name }}</td>
            <td>{{ user.email }}</td>
            <td>{{ user.role }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
