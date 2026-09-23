<script setup>
import { ref } from "vue";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const resetEndpoint = `${apiBaseUrl}/api/v2/auth/password-reset`;
const email = ref("");
const submitting = ref(false);
const error = ref("");
const confirmation = ref("");

async function submitReset() {
  submitting.value = true;
  error.value = "";
  confirmation.value = "";
  try {
    const response = await fetch(resetEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.value }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    confirmation.value = `If an account exists for ${result.email}, reset instructions are on the way.`;
  } catch (requestError) {
    error.value = "Unable to submit password reset.";
    console.error(requestError);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="recovery-shell">
    <p class="eyebrow">Northstar account</p>
    <h1>Reset your password</h1>
    <p class="intro">Enter the email connected to your account.</p>
    <form class="recovery-panel" data-testid="reset-form" @submit.prevent="submitReset">
      <label for="reset-email">Email address</label>
      <input id="reset-email" v-model="email" data-testid="reset-email" name="email" type="email" required>
      <button data-testid="reset-submit" type="submit" :disabled="submitting">
        {{ submitting ? "Sending…" : "Send reset instructions" }}
      </button>
      <p v-if="error" class="error" data-testid="reset-error" role="alert">{{ error }}</p>
      <p v-if="confirmation" class="success" data-testid="reset-success" role="status">{{ confirmation }}</p>
    </form>
  </main>
</template>

