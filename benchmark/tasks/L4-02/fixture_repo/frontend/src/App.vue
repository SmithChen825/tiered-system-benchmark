<script setup>
import { onMounted, ref } from "vue";
const apiBaseUrl=import.meta.env.VITE_API_BASE_URL||"http://127.0.0.1:8000"; const customers=ref([]); const error=ref("");
async function load(){const r=await fetch(`${apiBaseUrl}/api/customers`);if(!r.ok)throw new Error(`HTTP ${r.status}`);customers.value=await r.json();}
async function createSample(){error.value="";try{const r=await fetch(`${apiBaseUrl}/api/customers`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:"Sofia Rossi",email:"sofia.rossi@example.test"})});if(!r.ok)throw new Error(`HTTP ${r.status}`);await load();}catch(e){error.value="Unable to create customer.";console.error(e);}}
onMounted(()=>load().catch(e=>{error.value="Unable to load customers.";console.error(e);}));
</script>
<template><main><h1>Customer directory</h1><button data-testid="create-customer" @click="createSample">Create sample customer</button><p v-if="error" data-testid="error">{{ error }}</p><table data-testid="customer-table"><thead><tr><th>Name</th><th>Email</th><th>Status</th></tr></thead><tbody><tr v-for="customer in customers" :key="customer.id" data-testid="customer-row"><td>{{ customer.name }}</td><td>{{ customer.email }}</td><td>{{ customer.status }}</td></tr></tbody></table></main></template>
