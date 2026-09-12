// qrcode-generator ships no bundled type declarations; this covers only
// the small surface this project actually uses.
declare module "qrcode-generator" {
  type ErrorCorrectionLevel = "L" | "M" | "Q" | "H";

  interface QRCode {
    addData(data: string): void;
    make(): void;
    createSvgTag(opts?: {
      cellSize?: number;
      margin?: number;
      scalable?: boolean;
    }): string;
  }

  function qrcode(typeNumber: number, errorCorrectionLevel: ErrorCorrectionLevel): QRCode;

  export default qrcode;
}
