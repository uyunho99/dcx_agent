"use client";
import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { SNANode, SNALink } from "@/lib/types";

interface Props {
  nodes: SNANode[];
  links: SNALink[];
}

const COLOR_MAP: Record<string, string> = {
  product: "#6366f1",
  cluster: "#f59e0b",
  persona: "#10b981",
};

export default function SNAGraph({ nodes, links }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;
    const el = containerRef.current;
    el.innerHTML = "";

    const w = el.clientWidth || 360;
    const h = 340;
    const svg = d3.select(el).append("svg").attr("width", w).attr("height", h);

    const sim = d3
      .forceSimulation<SNANode>(nodes)
      .force("link", d3.forceLink<SNANode, SNALink>(links).id((d) => d.id).distance(120))
      .force("charge", d3.forceManyBody().strength(-400))
      .force("center", d3.forceCenter(w / 2, h / 2))
      .force("x", d3.forceX(w / 2).strength(0.1))
      .force("y", d3.forceY(h / 2).strength(0.1))
      .force("collision", d3.forceCollide<SNANode>().radius((d) => d.size + 15));

    const link = svg
      .append("g")
      .selectAll("line")
      .data(links)
      .enter()
      .append("line")
      .attr("stroke", "#e8e5e0")
      .attr("stroke-width", 2);

    const node = svg
      .append("g")
      .selectAll("circle")
      .data(nodes)
      .enter()
      .append("circle")
      .attr("r", (d) => d.size)
      .attr("fill", (d) => COLOR_MAP[d.type] || "#a8a29e")
      .attr("stroke", "#fff")
      .attr("stroke-width", 2)
      .style("cursor", "pointer")
      .call(
        d3.drag<SVGCircleElement, SNANode>()
          .on("start", (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      );

    const label = svg
      .append("g")
      .selectAll("text")
      .data(nodes)
      .enter()
      .append("text")
      .text((d) => (d.name.length > 8 ? d.name.substring(0, 8) + "..." : d.name))
      .attr("font-size", 10)
      .attr("text-anchor", "middle")
      .attr("dy", (d) => d.size + 12)
      .attr("fill", "#57534e");

    // Tooltip
    const tooltip = d3
      .select(el)
      .append("div")
      .style("position", "absolute")
      .style("display", "none")
      .style("background", "white")
      .style("border", "1px solid #e8e5e0")
      .style("border-radius", "12px")
      .style("padding", "10px 14px")
      .style("font-size", "13px")
      .style("box-shadow", "0 4px 16px rgba(0,0,0,0.08)")
      .style("pointer-events", "none")
      .style("z-index", "10");

    node
      .on("mouseover", (event, d) => {
        let html = `<div style="font-weight:700;color:#4338ca">${d.name}</div>`;
        if (d.type === "persona") {
          if (d.pain_point) html += `<div style="margin-top:4px;border-left:3px solid #fb7185;padding-left:6px"><span style="color:#e11d48;font-weight:600">Pain:</span> ${d.pain_point}</div>`;
          if (d.insight) html += `<div style="margin-top:4px;border-left:3px solid #34d399;padding-left:6px;background:#ecfdf5;border-radius:6px;padding:4px 6px"><span style="color:#059669;font-weight:600">Insight:</span> ${d.insight}</div>`;
        }
        if (d.type === "cluster") html += `<div style="color:#57534e">클러스터</div>`;
        tooltip.html(html).style("display", "block").style("left", event.offsetX + 15 + "px").style("top", event.offsetY - 15 + "px");
      })
      .on("mouseout", () => tooltip.style("display", "none"));

    sim.on("tick", () => {
      link
        .attr("x1", (d) => ((d.source as SNANode).x || 0))
        .attr("y1", (d) => ((d.source as SNANode).y || 0))
        .attr("x2", (d) => ((d.target as SNANode).x || 0))
        .attr("y2", (d) => ((d.target as SNANode).y || 0));
      node
        .attr("cx", (d) => (d.x = Math.max(d.size, Math.min(w - d.size, d.x || 0))))
        .attr("cy", (d) => (d.y = Math.max(d.size, Math.min(h - d.size, d.y || 0))));
      label.attr("x", (d) => d.x || 0).attr("y", (d) => d.y || 0);
    });

    return () => {
      sim.stop();
    };
  }, [nodes, links]);

  return <div ref={containerRef} className="relative w-full" style={{ minHeight: 340 }} />;
}
