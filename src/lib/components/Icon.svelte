<script>
  import {
    ArrowLeft,
    ArrowRight,
    ArrowUp,
    Bookmark,
    Briefcase,
    Building,
    Car,
    Check,
    ChevronDown,
    ChevronRight,
    CircleX,
    Clock,
    ExternalLink,
    GraduationCap,
    Grid2X2,
    HeartPulse,
    House,
    Layers,
    MapPin,
    Newspaper,
    PlayCircle,
    Search,
    Settings,
    ShieldCheck,
    Smartphone,
    TreePine,
    Trophy,
    Users
  } from '@lucide/svelte';

  export let name = 'newspaper';
  export let size = 24;
  export let strokeWidth = 2;
  export let className = '';

  const icons = {
    'arrow-left': ArrowLeft,
    'arrow-right': ArrowRight,
    'arrow-up': ArrowUp,
    bookmark: Bookmark,
    briefcase: Briefcase,
    building: Building,
    car: Car,
    check: Check,
    'chevron-down': ChevronDown,
    'chevron-right': ChevronRight,
    'circle-x': CircleX,
    clock: Clock,
    'external-link': ExternalLink,
    'graduation-cap': GraduationCap,
    grid: Grid2X2,
    'heart-pulse': HeartPulse,
    house: House,
    layers: Layers,
    'map-pin': MapPin,
    newspaper: Newspaper,
    'play-circle': PlayCircle,
    search: Search,
    settings: Settings,
    'shield-check': ShieldCheck,
    smartphone: Smartphone,
    tree: TreePine,
    trophy: Trophy,
    users: Users
  };

  $: IconComponent = icons[name] || Newspaper;
</script>

<svelte:component
  this={IconComponent}
  class={`lucide-icon ${className}`.trim()}
  {size}
  {strokeWidth}
  aria-hidden="true"
/>
