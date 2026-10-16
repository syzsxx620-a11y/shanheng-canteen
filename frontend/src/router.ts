import { createRouter, createWebHashHistory } from 'vue-router'
import { state, restore, loadCanteens } from './api'
export const router=createRouter({history:createWebHashHistory(),routes:[
 {path:'/login',component:()=>import('./pages/Login.vue')},
 {path:'/display/:id',component:()=>import('./pages/Display.vue')},
 {path:'/:pathMatch(.*)*',component:()=>import('./pages/Workspace.vue')}
]})
router.beforeEach(async to=>{
 if(to.path.startsWith('/display/'))return true
 if(!state.ready){await restore();state.ready=true;if(state.user)await loadCanteens()}
 if(!state.user&&to.path!=='/login')return '/login'
 if(state.user&&to.path==='/login')return '/'
 return true
})
