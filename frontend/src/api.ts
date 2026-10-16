import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
export interface User {id:string;username:string;role:'student'|'canteen_admin'|'system_admin';active:boolean;canteen_id:string|null}
export interface Dish {id:string;name:string;category:string;price:number;portion_g:number;kcal:number;protein:number;fat:number;carbs:number;ingredients:string[];allergens:string[]|null;image_url:string;nutrition_source:string;canteen_id:string;canteen_name:string;window_name:string;window_id:string;active:boolean;is_demo:boolean}
export const state = reactive({user:null as User|null, token:'',mode:'demo' as 'demo'|'real',canteens:[] as any[], ready:false})
let refreshing:Promise<boolean>|null=null
export async function restore(){
  if(!refreshing) refreshing=fetch('/api/v1/auth/refresh',{method:'POST',credentials:'include'}).then(async r=>{if(!r.ok)return false;const data=await r.json();state.token=data.access_token;state.user=data.user;return true}).catch(()=>false).finally(()=>{refreshing=null})
  return refreshing
}
export async function api<T=any>(path:string,options:RequestInit={},retry=true):Promise<T>{
  let res:Response
  try{res=await fetch('/api/v1'+path,{...options,credentials:'include',headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(state.token?{Authorization:'Bearer '+state.token}:{}),...options.headers}})}catch{ElMessage.error('连接服务失败，请检查后端是否启动');throw new Error('连接失败')}
  if(res.status===401&&retry&&!path.startsWith('/auth/')){if(await restore())return api(path,options,false);state.user=null;state.token='';window.location.hash='#/login'}
  if(!res.ok){let error:any={};try{error=await res.json()}catch{};const message=typeof error.detail==='string'?error.detail:res.status===422?'输入格式有误，请检查必填字段与数值范围':'操作失败，请稍后重试';ElMessage.error(message);throw new Error(message)}
  return res.json()
}
export const post=(path:string,data:unknown={})=>api(path,{method:'POST',body:JSON.stringify(data)})
export const put=(path:string,data:unknown)=>api(path,{method:'PUT',body:JSON.stringify(data)})
export async function login(username:string,password:string){const r=await post('/auth/login',{username,password});state.user=r.user;state.token=r.access_token;await loadCanteens()}
export async function logout(){await post('/auth/logout');state.user=null;state.token=''}
export async function loadCanteens(){state.canteens=await api('/canteens')}
export function localDate(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())}
export function dateText(value:string){return new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}
export function percent(value:number|null|undefined){return value==null?'待核验':(value*100).toFixed(1)+'%'}
export async function download(path:string,name:string){let res=await fetch('/api/v1'+path,{headers:{Authorization:'Bearer '+state.token}});if(res.status===401&&await restore())res=await fetch('/api/v1'+path,{headers:{Authorization:'Bearer '+state.token}});if(!res.ok){ElMessage.error('导出失败');return};const url=URL.createObjectURL(await res.blob());const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)}
