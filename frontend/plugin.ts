import type { StudioFrontendPlugin } from '@core/plugins/interface'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/life',
    name: 'life',
    component: () => import('./LifeView.vue'),
  },
]

const plugin: StudioFrontendPlugin = {
  name: 'life',
  displayName: 'Life',
  description: 'Mood tracking & wellness insights',
  basePath: '/life',
  routes,
  nav: {
    icon: '\uD83C\uDF3F',
    order: 1,
  },
}

export default plugin
