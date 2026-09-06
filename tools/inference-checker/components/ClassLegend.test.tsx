import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ClassLegend from "./ClassLegend";

test("legend with metrics renders one accessible button per class, without nested buttons", () => {
  const html = renderToStaticMarkup(createElement(ClassLegend, {
    labels: [{ name: "mud", readable: "Mud pumping", color: [255, 255, 0] }],
    hiddenClasses: new Set<number>(),
    onToggleClass: () => {},
    classIoUs: [{ classIndex: 0, iou: 25, intersection: 25, gtPixels: 50 }],
  }));
  expect(html.match(/<button\b/g)).toHaveLength(1);
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain("25.0%");
  expect(html).toContain("50.0%");
});
