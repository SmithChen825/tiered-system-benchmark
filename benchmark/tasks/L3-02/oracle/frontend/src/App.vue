<script setup>
import { onMounted, ref } from "vue";
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const order = ref(null); const loading = ref(true); const error = ref("");
onMounted(async () => { try { const response = await fetch(`${apiBaseUrl}/api/orders/ORD-2048`); if (!response.ok) throw new Error(`HTTP ${response.status}`); order.value = await response.json(); } catch (requestError) { error.value = "Unable to load order status."; console.error(requestError); } finally { loading.value = false; } });
</script>
<template><main class="account-shell"><p class="eyebrow">Northstar Dispatch</p><h1>Order status</h1><section class="account-panel" aria-live="polite"><p v-if="loading" data-testid="loading">Loading order…</p><p v-else-if="error" class="error" data-testid="error">{{ error }}</p><dl v-else-if="order" data-testid="order-panel"><div><dt>Order</dt><dd data-testid="order-id">{{ order.id }}</dd></div><div><dt>Customer</dt><dd>{{ order.customer }}</dd></div><div><dt>Status</dt><dd data-testid="order-status">{{ order.order_status }}</dd></div></dl></section></main></template>
