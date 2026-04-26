interface AlertBadgeProps {
  count: number;
}

export default function AlertBadge({ count }: AlertBadgeProps) {
  if (count <= 0) return null;

  return (
    <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold leading-none">
      {count > 99 ? "99+" : count}
    </span>
  );
}
