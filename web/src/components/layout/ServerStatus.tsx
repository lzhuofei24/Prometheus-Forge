import { useHealthCheck } from '../../hooks/useHealth';
import { Circle } from 'lucide-react';

export default function ServerStatus() {
  const { data, isLoading, isError } = useHealthCheck();

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-md border border-gray-200">
      <Circle
        className={`w-2 h-2 ${
          isLoading
            ? 'text-yellow-500 animate-pulse'
            : isError
            ? 'text-red-500'
            : 'text-green-500'
        }`}
        fill="currentColor"
      />
      <span className="text-xs text-gray-600">
        {isLoading
          ? '连接中...'
          : isError
          ? '后端离线'
          : data?.service || '后端在线'}
      </span>
    </div>
  );
}
