import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'life', component: () => import('./LifeView.vue') },
    { path: '/tokens', name: 'tokens', component: () => import('./TokensView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
