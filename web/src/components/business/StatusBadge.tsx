interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md' | 'lg';
}

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const getStatusConfig = (status: string) => {
    const configs: Record<string, { label: string; className: string }> = {
      started: { label: '已启动', className: 'bg-blue-100 text-blue-800' },
      writing: { label: '写作中', className: 'bg-yellow-100 text-yellow-800' },
      critiquing: { label: '审稿中', className: 'bg-purple-100 text-purple-800' },
      completed: { label: '已完成', className: 'bg-green-100 text-green-800' },
      failed: { label: '失败', className: 'bg-red-100 text-red-800' },
    };
    return configs[status] || { label: status, className: 'bg-gray-100 text-gray-800' };
  };

  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-1.5 text-base',
  };

  const config = getStatusConfig(status);

  return (
    <span
      className={`inline-block rounded-full font-medium ${config.className} ${sizeClasses[size]}`}
    >
      {config.label}
    </span>
  );
}
