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
    HardDrive,
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
    TreeDeciduous,
    Trophy,
    Users
  } from '@lucide/svelte';

  export let name = 'newspaper-clipping';
  export let size = 24;
  export let strokeWidth = 2;
  export let className = '';

  /* Keep Forest City News' original icon identities stable. The keys below
     intentionally retain the names used before the Svelte/Lucide migration.
     Where Lucide names the same concept differently, that translation happens
     here instead of silently changing the icon chosen by the UI. */
  const icons = {
    'arrow-left': ArrowLeft,
    'arrow-right': ArrowRight,
    'arrow-up': ArrowUp,
    bookmark: Bookmark,
    'bookmark-simple': Bookmark,
    briefcase: Briefcase,
    building: Building,
    buildings: Building,
    car: Car,
    check: Check,
    'caret-down': ChevronDown,
    'caret-right': ChevronRight,
    'chevron-down': ChevronDown,
    'chevron-right': ChevronRight,
    'circle-x': CircleX,
    'x-circle': CircleX,
    clock: Clock,
    'clock-countdown': Clock,
    'device-mobile': Smartphone,
    'external-link': ExternalLink,
    'gear-six': Settings,
    'graduation-cap': GraduationCap,
    grid: HardDrive,
    'hard-drives': HardDrive,
    heartbeat: HeartPulse,
    'heart-pulse': HeartPulse,
    house: House,
    layers: Layers,
    stack: Layers,
    'map-pin': MapPin,
    newspaper: Newspaper,
    'newspaper-clipping': Newspaper,
    'play-circle': PlayCircle,
    search: Search,
    'magnifying-glass': Search,
    settings: Settings,
    'shield-check': ShieldCheck,
    smartphone: Smartphone,
    tree: TreeDeciduous,
    trophy: Trophy,
    users: Users,
    'users-three': Users
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
