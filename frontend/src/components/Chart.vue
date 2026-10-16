<script setup lang="ts">
import {onMounted,onBeforeUnmount,ref,watch,nextTick} from 'vue'
import * as echarts from 'echarts'
const props=defineProps<{option:any}>();const root=ref<HTMLElement>();let chart:echarts.ECharts|undefined;let observer:ResizeObserver
onMounted(()=>{chart=echarts.init(root.value!);chart.setOption(props.option);observer=new ResizeObserver(()=>chart?.resize());observer.observe(root.value!)})
watch(()=>props.option,async value=>{await nextTick();chart?.setOption(value,true)},{deep:true})
onBeforeUnmount(()=>{observer?.disconnect();chart?.dispose()})
</script>
<template><div class="chart" ref="root" role="img" aria-label="统计图表" /></template>
