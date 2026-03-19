export default function Spinner({ size = 20 }: { size?: number }) {
  return (
    <div
      className="border-2 border-stone-200 border-t-indigo-500 rounded-full animate-spin"
      style={{ width: size, height: size }}
    />
  );
}
