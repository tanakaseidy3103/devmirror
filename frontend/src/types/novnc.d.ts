/**
 * noVNC の型定義
 *
 * @novnc/novnc は型定義を同梱していないため、
 * 使う部分だけここで宣言する。
 */
declare module "@novnc/novnc" {
  export interface RFBOptions {
    credentials?: { password?: string };
    shared?: boolean;
    repeaterID?: string;
    wsProtocols?: string[];
  }

  export default class RFB {
    constructor(target: HTMLElement, url?: string, options?: RFBOptions);
    scaleViewport: boolean;
    resizeSession: boolean;
    viewOnly: boolean;
    clipViewport: boolean;
    focusOnClick: boolean;
    disconnect(): void;
    addEventListener(type: string, listener: (event: Event) => void): void;
    removeEventListener(type: string, listener: (event: Event) => void): void;
  }
}
