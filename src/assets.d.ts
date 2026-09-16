// Asset imports are resolved by rollup-plugin-import-assets (see
// @decky/rollup) into a URL string served from the plugin's local
// decky-loader asset endpoint at runtime.
declare module "*.svg" {
  const url: string;
  export default url;
}
