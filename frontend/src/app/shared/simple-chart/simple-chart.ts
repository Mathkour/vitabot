import { Component, computed, input } from '@angular/core';

export interface SimpleChartData {
  chartType: 'bar' | 'pie';
  title: string;
  labels: string[];
  values: number[];
}

const PIE_SLICE_CAP = 8;

interface BarRow {
  label: string;
  valueLabel: string;
  /** Bar length as a percentage of the largest value. */
  percent: number;
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

  /** One number format for the whole chart: two decimals if any value has
   * a fraction, none otherwise (never 61,377.5 next to 32,819.79). Western
   * digits with thousands separators, matching the answer text above it. */
  private static formatter(values: number[]): Intl.NumberFormat {
    const decimals = values.some((v) => Math.round(v * 100) % 100 !== 0) ? 2 : 0;
    return new Intl.NumberFormat('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }

  /** Horizontal bars, one row per item: long names (product, customer)
   * get the full row width and wrap instead of being cut to "BABY JOY BO…"
   * under a narrow vertical bar. */
  readonly barRows = computed<BarRow[]>(() => {
    const d = this.data();
    const max = Math.max(...d.values, 0) || 1;
    const fmt = SimpleChart.formatter(d.values);
    return d.values.map((v, i) => ({
      label: d.labels[i] ?? '',
      valueLabel: fmt.format(v),
      percent: Math.max(0, (v / max) * 100),
    }));
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
