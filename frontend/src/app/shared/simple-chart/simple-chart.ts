import { Component, computed, input } from '@angular/core';

export interface SimpleChartData {
  chartType: 'bar' | 'pie';
  title: string;
  labels: string[];
  values: number[];
}

const PIE_SLICE_CAP = 8;

interface BarGeometry {
  x: number;
  y: number;
  width: number;
  height: number;
  value: number;
  valueLabel: string;
  label: string;
  labelX: number;
  valueY: number;
}

interface PieSlice {
  path: string;
  color: string;
  label: string;
  value: number;
  percent: number;
}

@Component({
  selector: 'app-simple-chart',
  templateUrl: './simple-chart.html',
  styleUrl: './simple-chart.scss',
})
export class SimpleChart {
  readonly data = input.required<SimpleChartData>();

  private static formatValue(value: number): string {
    const rounded = Math.round(value * 100) / 100;
    return rounded.toLocaleString();
  }

  private static truncateLabel(label: string, maxChars: number): string {
    return label.length > maxChars ? `${label.slice(0, maxChars - 1)}…` : label;
  }

  readonly barChart = computed(() => {
    const d = this.data();
    const values = d.values;
    const width = 320;
    const height = 180;
    const paddingTop = 26;
    const paddingBottom = 34;
    const paddingX = 10;
    const plotWidth = width - paddingX * 2;
    const plotHeight = height - paddingTop - paddingBottom;
    const max = Math.max(...values, 1);
    const n = Math.max(values.length, 1);
    const slot = plotWidth / n;
    const barWidth = Math.max(6, Math.min(28, slot * 0.55));
    const baselineY = paddingTop + plotHeight;
    const labelMaxChars = slot > 50 ? 12 : slot > 32 ? 8 : 5;

    const bars: BarGeometry[] = values.map((v, i) => {
      const barHeight = max > 0 ? (Math.max(v, 0) / max) * plotHeight : 0;
      const x = paddingX + i * slot + (slot - barWidth) / 2;
      const y = baselineY - barHeight;
      return {
        x,
        y,
        width: barWidth,
        height: barHeight,
        value: v,
        valueLabel: SimpleChart.formatValue(v),
        label: SimpleChart.truncateLabel(d.labels[i] ?? '', labelMaxChars),
        labelX: x + barWidth / 2,
        valueY: y - 6,
      };
    });

    return { width, height, bars, baselineY, paddingX, plotWidth };
  });

  readonly pieChart = computed(() => {
    const d = this.data();
    let labels = d.labels;
    let values = d.values;

    if (labels.length > PIE_SLICE_CAP) {
      const topLabels = labels.slice(0, PIE_SLICE_CAP - 1);
      const topValues = values.slice(0, PIE_SLICE_CAP - 1);
      const restTotal = values.slice(PIE_SLICE_CAP - 1).reduce((sum, v) => sum + v, 0);
      labels = [...topLabels, 'Other'];
      values = [...topValues, restTotal];
    }

    const total = values.reduce((sum, v) => sum + Math.max(v, 0), 0) || 1;
    const cx = 90;
    const cy = 90;
    const r = 78;

    const isSingleSlice = values.filter((v) => v > 0).length <= 1;

    let angleStart = -90;
    const slices: PieSlice[] = values.map((v, i) => {
      const fraction = Math.max(v, 0) / total;
      const angle = fraction * 360;
      const largeArc = angle > 180 ? 1 : 0;
      const startRad = (Math.PI / 180) * angleStart;
      const endRad = (Math.PI / 180) * (angleStart + angle);
      const x1 = cx + r * Math.cos(startRad);
      const y1 = cy + r * Math.sin(startRad);
      const x2 = cx + r * Math.cos(endRad);
      const y2 = cy + r * Math.sin(endRad);
      const path = `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
      angleStart += angle;
      return {
        path,
        color: `var(--simple-chart-series-${(i % PIE_SLICE_CAP) + 1})`,
        label: labels[i] ?? '',
        value: v,
        percent: Math.round(fraction * 100),
      };
    });

    return { cx, cy, r, slices, isSingleSlice, singleColor: 'var(--simple-chart-series-1)' };
  });
}
