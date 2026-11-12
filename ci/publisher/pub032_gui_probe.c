#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
static LRESULT CALLBACK wp(HWND h,UINT m,WPARAM w,LPARAM l){
 if(m==WM_CLOSE){DestroyWindow(h);return 0;}
 if(m==WM_DESTROY){PostQuitMessage(0);return 0;}
 return DefWindowProcW(h,m,w,l);
}
int WINAPI WinMain(HINSTANCE inst,HINSTANCE prev,LPSTR cmd,int show){
 WNDCLASSW c;HWND h;MSG msg;
 (void)prev;(void)cmd;(void)show;
 ZeroMemory(&c,sizeof(c));c.hInstance=inst;c.lpfnWndProc=wp;
 c.lpszClassName=L"PUB032GUIProbe";
 if(!RegisterClassW(&c))return 100;
 h=CreateWindowExW(0,L"PUB032GUIProbe",L"PUB032_WIN32_WINDOW_PROBE",
 WS_OVERLAPPEDWINDOW,25,25,350,120,NULL,NULL,inst,NULL);
 if(!h){return 101;}
 ShowWindow(h,SW_SHOW);UpdateWindow(h);
 while(GetMessageW(&msg,0,0,0)>0){TranslateMessage(&msg);DispatchMessageW(&msg);}
 return 0;
}
