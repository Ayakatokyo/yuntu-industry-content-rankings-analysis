import fs from "node:fs/promises";
import process from "node:process";
import { dirname } from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("usage: build_highlight_workbook.mjs INPUT.json OUTPUT.xlsx");
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const rows = Array.isArray(payload) ? payload : (payload.rows || []);
const headers = ["品牌", "视觉类型", "素材排名", "素材 ID", "素材标题", "画面类型", "高光帧图片", "秒数", "点击峰值排名", "点击指数"];
const textHeaders = new Set(["素材 ID"]);
const values = rows.map((row) => headers.map((header) => {
  if (header === "高光帧图片") return null;
  const value = row[header] ?? null;
  return textHeaders.has(header) && value !== null && value !== "" ? `'${value}` : value;
}));
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("高光帧资产");
sheet.showGridLines = false;
sheet.getRangeByIndexes(0, 0, 1, headers.length).values = [headers];
if (values.length) sheet.getRangeByIndexes(1, 0, values.length, headers.length).values = values;

const endRow = Math.max(1, values.length + 1);
const used = sheet.getRange(`A1:J${endRow}`);
used.format.wrapText = true;
used.format.verticalAlignment = "center";
used.format.borders = { preset: "all", style: "thin", color: "#dfcfbd" };
sheet.getRange("A1:J1").format = {
  fill: "#2c1810",
  font: { bold: true, color: "#ffffff" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A1:J1").format.rowHeight = 30;
sheet.getRange(`C2:C${endRow}`).format.numberFormat = "0";
sheet.getRange(`D2:D${endRow}`).format.numberFormat = "@";
sheet.getRange(`H2:H${endRow}`).format.numberFormat = "0";
sheet.getRange(`I2:I${endRow}`).format.numberFormat = "0";
sheet.getRange(`J2:J${endRow}`).format.numberFormat = "0.00";
sheet.getRange("A:A").format.columnWidth = 18;
sheet.getRange("B:B").format.columnWidth = 14;
sheet.getRange("C:C").format.columnWidth = 10;
sheet.getRange("D:D").format.columnWidth = 22;
sheet.getRange("E:E").format.columnWidth = 42;
sheet.getRange("F:F").format.columnWidth = 22;
sheet.getRange("G:G").format.columnWidth = 18;
sheet.getRange("H:J").format.columnWidth = 12;
if (values.length) sheet.getRange(`A2:J${endRow}`).format.rowHeight = 118;
sheet.freezePanes.freezeRows(1);
const table = sheet.tables.add(`A1:J${endRow}`, true, "HighlightFramesTable");
table.showFilterButton = true;

for (let index = 0; index < rows.length; index += 1) {
  const imagePath = rows[index].__image_path;
  if (!imagePath) continue;
  try {
    const bytes = await fs.readFile(imagePath);
    const ext = String(imagePath).toLowerCase().endsWith(".png") ? "png" : "jpeg";
    const dataUrl = `data:image/${ext};base64,${Buffer.from(bytes).toString("base64")}`;
    sheet.images.add({
      dataUrl,
      anchor: { from: { row: index + 1, col: 6 }, extent: { widthPx: 92, heightPx: 112 } },
    });
  } catch {
    // Keep the row and its source path even when an individual image is unavailable.
  }
}

await fs.mkdir(dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
