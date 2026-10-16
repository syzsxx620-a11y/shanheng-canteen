<script setup lang="ts">
import {ref,onBeforeUnmount} from 'vue'
const emit=defineEmits<{selected:[file:File,roi:number[]]}>(),url=ref(''),file=ref<File>(),area=ref([0,0,1,1]),start=ref<number[]|null>(null),root=ref<HTMLElement>()
function upload(event:Event){const input=event.target as HTMLInputElement;const f=input.files?.[0];if(!f)return;if(url.value)URL.revokeObjectURL(url.value);file.value=f;url.value=URL.createObjectURL(f);area.value=[0,0,1,1];emit('selected',f,area.value)}
function point(e:PointerEvent){const r=root.value!.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))]}
function down(e:PointerEvent){if(!file.value)return;start.value=point(e);root.value!.setPointerCapture(e.pointerId)}
function move(e:PointerEvent){if(!start.value)return;const end=point(e),s=start.value;area.value=[Math.min(s[0],end[0]),Math.min(s[1],end[1]),Math.abs(s[0]-end[0]),Math.abs(s[1]-end[1])]}
function up(){if(!start.value)return;start.value=null;if(area.value[2]<.02||area.value[3]<.02)area.value=[0,0,1,1];if(file.value)emit('selected',file.value,area.value)}
onBeforeUnmount(()=>{if(url.value)URL.revokeObjectURL(url.value)})
</script>
<template><div class="roi-upload"><label class="upload-label"><input type="file" accept="image/jpeg,image/png" @change="upload"><b>上传餐盘照片</b><span>JPG / PNG，最大10MB</span></label><p class="small muted">请拖拽框选餐盘内部有效区域；只保存选中区域。不要包含人脸或其他餐盘。</p><div v-if="url" class="roi-image" ref="root" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up"><img :src="url" alt="框选餐盘区域" draggable="false"><div class="roi-box" :style="{left:area[0]*100+'%',top:area[1]*100+'%',width:area[2]*100+'%',height:area[3]*100+'%'}"></div></div></div></template>
