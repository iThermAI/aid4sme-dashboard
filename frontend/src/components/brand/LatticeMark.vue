<script setup>
defineProps({ animated: { type: Boolean, default: false } })
</script>

<template>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="43 42 714 816" class="lattice" :class="{ animated }" role="img" aria-label="iThermAI"><defs>
    
    <filter id="lm-soft-glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3" result="coloredBlur" />
      <feMerge>
        <feMergeNode in="coloredBlur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    
    <linearGradient id="lm-gradNodeBlue" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4aa3ff" />
      <stop offset="100%" stop-color="#002a55" />
    </linearGradient>

    <linearGradient id="lm-gradNodeDark" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#a0b0bc" />
      <stop offset="100%" stop-color="#121619" />
    </linearGradient>

    <linearGradient id="lm-pipeBlue" x1="0%" y1="0%" x2="100%" y2="0%" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#001a33" />
      <stop offset="50%" stop-color="#2a6fc4" />
      <stop offset="100%" stop-color="#001a33" />
    </linearGradient>

    <linearGradient id="lm-pipeSilver" x1="0%" y1="0%" x2="100%" y2="0%" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#2a2a2a" />
      <stop offset="50%" stop-color="#777777" />
      <stop offset="100%" stop-color="#2a2a2a" />
    </linearGradient>
  </defs>
  <g stroke-linecap="round" stroke-linejoin="round" stroke-width="10">
    <polyline points="400,70 564.5,165 729,260 729,450 729,640 564.5,735 400,830 235.5,735 71,640 71,450 71,260 235.5,165 400,70" fill="none" stroke="#222" />
    <g stroke="url(#lm-pipeSilver)">
        <path d="M564.5 165 L400 260 M564.5 165 L564.5 355" />
        <path d="M729 450 L564.5 355 M729 450 L564.5 545" />
        <path d="M564.5 735 L564.5 545 M564.5 735 L400 640" />
        <path d="M235.5 735 L400 640 M235.5 735 L235.5 545" />
        <path d="M71 450 L235.5 545 M71 450 L235.5 355" />
        <path d="M235.5 165 L235.5 355 M235.5 165 L400 260" />
    </g>
    <g stroke="url(#lm-pipeBlue)">
        <polygon points="400,260 564.5,355 564.5,545 400,640 235.5,545 235.5,355" fill="none" />
        <path d="M400 450 L400 260 M400 450 L564.5 355 M400 450 L564.5 545 M400 450 L400 640 M400 450 L235.5 545 M400 450 L235.5 355" />
        <path d="M400 260 L400 70 M564.5 355 L729 260 M564.5 545 L729 640 M400 640 L400 830 M235.5 545 L71 640 M235.5 355 L71 260" />
    </g>
  </g>
  <g class="lm-flow-base lm-flow-group-1">
      <path d="M400 70 L400 260 L400 450 L400 640 L400 830" /> 
      <path d="M564.5 355 L564.5 545" /> 
      <path d="M235.5 545 L235.5 355" />
  </g>
  <g class="lm-flow-base lm-flow-group-2">
      <path d="M71 260 L235.5 355 L400 450 L564.5 545 L729 640" />
      <path d="M400 260 L564.5 355" />
      <path d="M400 640 L235.5 545" />
  </g>
  <g class="lm-flow-base lm-flow-group-3">
      <path d="M729 260 L564.5 355 L400 450 L235.5 545 L71 640" />
      <path d="M235.5 355 L400 260" />
      <path d="M564.5 545 L400 640" />
  </g>
  <g class="lm-flow-base lm-flow-silver">
      <polygon points="400,70 564.5,165 729,260 729,450 729,640 564.5,735 400,830 235.5,735 71,640 71,450 71,260 235.5,165" />
      <path d="M564.5 165 L564.5 355 L729 450 L564.5 545 L564.5 735" />
      <path d="M235.5 735 L235.5 545 L71 450 L235.5 355 L235.5 165" />
  </g>
  <g>
    <g fill="url(#lm-gradNodeDark)">
        <circle cx="564.5" cy="165" r="25" class="lm-living-node" />
        <circle cx="729" cy="450" r="25" class="lm-living-node" />
        <circle cx="564.5" cy="735" r="25" class="lm-living-node" />
        <circle cx="235.5" cy="735" r="25" class="lm-living-node" />
        <circle cx="71" cy="450" r="25" class="lm-living-node" />
        <circle cx="235.5" cy="165" r="25" class="lm-living-node" />
    </g>
    <g fill="url(#lm-gradNodeBlue)">
        <circle cx="400" cy="260" r="25" class="lm-living-node" />
        <circle cx="564.5" cy="355" r="25" class="lm-living-node" />
        <circle cx="564.5" cy="545" r="25" class="lm-living-node" />
        <circle cx="400" cy="640" r="25" class="lm-living-node" />
        <circle cx="235.5" cy="545" r="25" class="lm-living-node" />
        <circle cx="235.5" cy="355" r="25" class="lm-living-node" />
        <circle cx="400" cy="70" r="25" class="lm-living-node" />
        <circle cx="729" cy="260" r="25" class="lm-living-node" />
        <circle cx="729" cy="640" r="25" class="lm-living-node" />
        <circle cx="400" cy="830" r="25" class="lm-living-node" />
        <circle cx="71" cy="640" r="25" class="lm-living-node" />
        <circle cx="71" cy="260" r="25" class="lm-living-node" />
    </g>
    <circle cx="400" cy="450" r="25" fill="url(#lm-gradNodeBlue)" class="lm-living-node" />
  </g>
</svg>
</template>

<style scoped>
.lattice { display: block; height: 100%; width: auto; overflow: visible; }
.lattice :deep(.lm-flow-base) {
  fill: none; stroke-width: 4; stroke-linecap: round; stroke-dasharray: 50 450;
  filter: url(#lm-soft-glow); opacity: 0;
}
.lattice.animated :deep(.lm-flow-base) { opacity: 0.55; }
.lattice :deep(.lm-flow-group-1), .lattice :deep(.lm-flow-group-2), .lattice :deep(.lm-flow-group-3) { stroke: #70bfff; }
.lattice :deep(.lm-flow-silver) { stroke: #ffffff; stroke-dasharray: 40 400; }
.lattice.animated :deep(.lm-flow-group-1) { animation: lm-flow 9s linear infinite; }
.lattice.animated :deep(.lm-flow-group-2) { animation: lm-flow 9s linear infinite; animation-delay: -3s; }
.lattice.animated :deep(.lm-flow-group-3) { animation: lm-flow 9s linear infinite; animation-delay: -6s; }
.lattice.animated :deep(.lm-flow-silver) { animation: lm-flow 10s linear infinite reverse; }
.lattice :deep(.lm-living-node) { transform-box: fill-box; transform-origin: center; }
.lattice.animated :deep(.lm-living-node) { animation: lm-beat 4s ease-in-out infinite; }
@keyframes lm-flow { from { stroke-dashoffset: 800; } to { stroke-dashoffset: 0; } }
@keyframes lm-beat { 50% { transform: scale(1.08); opacity: 0.95; } }
@media (prefers-reduced-motion: reduce) {
  .lattice.animated :deep(*) { animation: none !important; }
}
</style>
