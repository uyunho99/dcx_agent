import type { TableHTMLAttributes } from "react";
export type TableProps = TableHTMLAttributes<HTMLTableElement>;
export function Table({ className = "", ...props }: TableProps) { return <table {...props} className={`ds-tbl ${className}`} />; }
