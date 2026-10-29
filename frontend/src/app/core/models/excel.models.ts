export interface ExcelRow {
  id: string;
  row_data: Record<string, string>;
}

export interface ExcelTable {
  columns: string[];
  rows: ExcelRow[];
}
