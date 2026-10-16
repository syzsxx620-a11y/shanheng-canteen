<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import {useRoute} from 'vue-router'
import {Sprout,Leaf,ScanLine} from 'lucide-vue-next'
const route=useRoute(),data=ref<any>(null),error=ref('');let timer:ReturnType<typeof setInterval>
async function load(){try{const r=await fetch(`/api/v1/display/${route.params.id}?mode=${route.query.mode==='real'?'real':'demo'}`);if(!r.ok)throw new Error();data.value=await r.json();error.value=''}catch{error.value='监测服务暂时不可用，正在重试'}}
onMounted(()=>{load();timer=setInterval(load,3000)});onBeforeUnmount(()=>clearInterval(timer))
</script>
<template><div class="display-page"><div class="brand"><span class="brand-mark"><Sprout/></span><b>膳衡 · 智慧回收</b></div><span class="eyebrow">EVERY PLATE MATTERS</span><h1>珍惜每一餐，<br>从刚刚好开始。</h1><div class="display-result"><ScanLine :size="40"/><template v-if="data?.latest"><span>{{data.mode==='demo'?'模拟监测 / 非模型结果':'匿名餐盘监测'}}</span><strong>{{data.latest.grade}}</strong><p>{{data.latest.reminder}}</p><small>{{data.latest.status==='pending'?'检测结果待人工核验':'剩余面积占比 '+((data.latest.area_ratio||0)*100).toFixed(1)+'% · 非重量浪费率'}}</small></template><p v-else>{{error||'等待下一份餐盘…'}}</p></div><div class="display-bottom"><Leaf :size="25"/><span>今日已记录 <b>{{data?.today_count||0}}</b> 份餐盘</span><span>匿名监测 · 不关联个人身份</span></div><p v-if="error" class="error-text">{{error}}</p></div></template>
