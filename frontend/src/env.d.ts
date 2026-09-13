/// <reference types="vite/client" />

import "axios";

declare module "axios" {
  export interface AxiosRequestConfig {
    /** 为 true 时不弹出全局错误提示，由调用方自行处理 */
    silent?: boolean;
  }
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}
