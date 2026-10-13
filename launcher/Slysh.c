/*
 * Slysh GUI launcher (no console). Mirrors Slysh.bat environment and startup.
 * Build: see launcher/README.md
 */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <stdio.h>
#include <dwmapi.h>
#include <math.h>
#include <shlobj.h>
#include <string.h>

#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "dwmapi.lib")

#ifndef DWMWA_WINDOW_CORNER_PREFERENCE
#define DWMWA_WINDOW_CORNER_PREFERENCE 33
#endif
#ifndef DWMWCP_ROUND
#define DWMWCP_ROUND 2
#endif

static void show_error(const wchar_t *title, const wchar_t *text) {
    MessageBoxW(NULL, text, title, MB_OK | MB_ICONERROR);
}

static int path_exists(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

static int path_is_directory(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY);
}

static int path_is_prefix_of(const wchar_t *prefix, const wchar_t *path) {
    size_t plen;

    if (prefix[0] == L'\0' || path[0] == L'\0')
        return 0;
    plen = wcslen(prefix);
    if (_wcsnicmp(path, prefix, plen) != 0)
        return 0;
    if (path[plen] == L'\0' || path[plen] == L'\\')
        return 1;
    return 0;
}

static int append_path(wchar_t *dest, size_t dest_chars, const wchar_t *suffix) {
    if (PathCombineW(dest, dest, suffix) == NULL)
        return 0;
    return 1;
}

static int set_env_pair(const wchar_t *name, const wchar_t *value) {
    if (!SetEnvironmentVariableW(name, value))
        return 0;
    return 1;
}

static void unset_env(const wchar_t *name) {
    SetEnvironmentVariableW(name, NULL);
}

static void clear_dev_python_env(void) {
    unset_env(L"PYTHONPATH");
    unset_env(L"PYTHONHOME");
    unset_env(L"UV_PROJECT");
    unset_env(L"UV_WORKING_DIRECTORY");
    unset_env(L"PYWEBVIEW_GUI");
    unset_env(L"WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS");
}

static int prepend_path_bin(const wchar_t *root) {
    wchar_t bin[MAX_PATH * 2];
    wchar_t old_path[32768];
    wchar_t new_path[32768];
    DWORD n;

    if (!PathCombineW(bin, root, L"bin"))
        return 0;
    n = GetEnvironmentVariableW(L"PATH", old_path, (DWORD)(sizeof(old_path) / sizeof(old_path[0])));
    if (n == 0 || n >= sizeof(old_path) / sizeof(old_path[0])) {
        old_path[0] = L'\0';
    }
    if (old_path[0] == L'\0') {
        swprintf_s(new_path, sizeof(new_path) / sizeof(new_path[0]), L"%s", bin);
    } else {
        swprintf_s(new_path, sizeof(new_path) / sizeof(new_path[0]), L"%s;%s", bin, old_path);
    }
    return SetEnvironmentVariableW(L"PATH", new_path) != 0;
}

static void splash_pump_messages(void);

static int run_process_wait(const wchar_t *exe, const wchar_t *cmdline, const wchar_t *cwd, DWORD *exit_code, int pump_splash) {
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    wchar_t cmd_copy[32768];
    DWORD flags = CREATE_NO_WINDOW;

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));

    if (wcslen(cmdline) >= sizeof(cmd_copy) / sizeof(cmd_copy[0]))
        return 0;
    wcscpy_s(cmd_copy, sizeof(cmd_copy) / sizeof(cmd_copy[0]), cmdline);

    if (!CreateProcessW(exe, cmd_copy, NULL, NULL, FALSE, flags, NULL, cwd, &si, &pi)) {
        return 0;
    }
    if (pump_splash) {
        for (;;) {
            DWORD wait = WaitForSingleObject(pi.hProcess, 50);
            splash_pump_messages();
            if (wait == WAIT_OBJECT_0)
                break;
        }
    } else {
        WaitForSingleObject(pi.hProcess, INFINITE);
    }
    if (exit_code) {
        GetExitCodeProcess(pi.hProcess, exit_code);
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 1;
}

static int run_process(const wchar_t *exe, const wchar_t *cmdline, const wchar_t *cwd, DWORD *exit_code) {
    return run_process_wait(exe, cmdline, cwd, exit_code, 0);
}

#define LAUNCH_FAIL_PROBE_MS 3000

/* Returns 1 if process still running after probe, 2 if exited early, 0 on CreateProcess failure. */
static int run_process_launch(const wchar_t *exe, const wchar_t *cmdline, const wchar_t *cwd, DWORD *exit_code) {
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    wchar_t cmd_copy[32768];
    DWORD flags = CREATE_NO_WINDOW;
    ULONGLONG deadline;
    DWORD code = 0;

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));

    if (wcslen(cmdline) >= sizeof(cmd_copy) / sizeof(cmd_copy[0]))
        return 0;
    wcscpy_s(cmd_copy, sizeof(cmd_copy) / sizeof(cmd_copy[0]), cmdline);

    if (!CreateProcessW(exe, cmd_copy, NULL, NULL, FALSE, flags, NULL, cwd, &si, &pi)) {
        return 0;
    }

    deadline = GetTickCount64() + LAUNCH_FAIL_PROBE_MS;
    for (;;) {
        DWORD wait = WaitForSingleObject(pi.hProcess, 50);
        splash_pump_messages();
        if (wait == WAIT_OBJECT_0) {
            if (exit_code) {
                GetExitCodeProcess(pi.hProcess, exit_code);
            } else {
                GetExitCodeProcess(pi.hProcess, &code);
            }
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return 2;
        }
        if (GetTickCount64() >= deadline) {
            if (exit_code) {
                *exit_code = STILL_ACTIVE;
            }
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return 1;
        }
    }
}

static int write_launch_error(const wchar_t *root, DWORD exit_code) {
    wchar_t log_path[MAX_PATH * 2];
    wchar_t err_file[MAX_PATH * 2];
    SYSTEMTIME st;
    FILE *fp = NULL;

    if (!PathCombineW(err_file, root, L"launch-last-error.txt"))
        return 0;
    if (ExpandEnvironmentStringsW(L"%LOCALAPPDATA%\\Slysh\\logs", log_path,
                                (DWORD)(sizeof(log_path) / sizeof(log_path[0]))) == 0) {
        log_path[0] = L'\0';
    }
    GetLocalTime(&st);
    if (_wfopen_s(&fp, err_file, L"a, ccs=UTF-8") != 0 || fp == NULL)
        return 0;
    fwprintf(fp,
             L"[%04u-%02u-%02u %02u:%02u:%02u] pythonw exit code: %lu\n",
             (unsigned)st.wYear,
             (unsigned)st.wMonth,
             (unsigned)st.wDay,
             (unsigned)st.wHour,
             (unsigned)st.wMinute,
             (unsigned)st.wSecond,
             (unsigned long)exit_code);
    if (log_path[0] != L'\0') {
        fwprintf(fp, L"Logs: %s\n", log_path);
    }
    fclose(fp);
    return 1;
}

static void show_app_exit_error(DWORD exit_code) {
    wchar_t log_path[MAX_PATH * 2];
    wchar_t msg[1024];

    if (ExpandEnvironmentStringsW(L"%LOCALAPPDATA%\\Slysh\\logs", log_path,
                                (DWORD)(sizeof(log_path) / sizeof(log_path[0]))) == 0) {
        log_path[0] = L'\0';
    }
    if (log_path[0] != L'\0') {
        swprintf_s(msg,
                   sizeof(msg) / sizeof(msg[0]),
                   L"Slysh завершился с ошибкой (код %lu).\n\n"
                   L"Подробности: %s\n"
                   L"(файл startup-crash.log при сбое Python)\n"
                   L"Также см. launch-last-error.txt в папке программы.",
                   (unsigned long)exit_code,
                   log_path);
    } else {
        swprintf_s(msg,
                   sizeof(msg) / sizeof(msg[0]),
                   L"Slysh завершился с ошибкой (код %lu).\n\n"
                   L"См. launch-last-error.txt в папке программы.",
                   (unsigned long)exit_code);
    }
    show_error(L"Slysh!", msg);
}

static int set_install_uv_env(const wchar_t *root) {
    wchar_t uv_python[MAX_PATH * 2];

    if (!PathCombineW(uv_python, root, L"runtime\\python"))
        return 0;
    return set_env_pair(L"UV_PYTHON_INSTALL_DIR", uv_python);
}

static int read_pyvenv_home(const wchar_t *root, wchar_t *home, size_t home_chars) {
    wchar_t cfg_path[MAX_PATH * 2];
    FILE *fp = NULL;
    wchar_t wline[512];
    const wchar_t *prefix = L"home = ";
    size_t plen = wcslen(prefix);
    wchar_t *p;

    home[0] = L'\0';
    if (!PathCombineW(cfg_path, root, L".venv\\pyvenv.cfg"))
        return 0;
    if (_wfopen_s(&fp, cfg_path, L"r, ccs=UTF-8") != 0 || fp == NULL) {
        if (_wfopen_s(&fp, cfg_path, L"r") != 0 || fp == NULL)
            return 0;
    }
    while (fgetws(wline, (int)(sizeof(wline) / sizeof(wline[0])), fp) != NULL) {
        if (wcsncmp(wline, prefix, plen) != 0)
            continue;
        p = wline + plen;
        while (*p == L' ' || *p == L'\t')
            p++;
        wcscpy_s(home, home_chars, p);
        for (p = home + wcslen(home); p > home && (p[-1] == L'\n' || p[-1] == L'\r'); p--)
            *(--p) = L'\0';
        fclose(fp);
        return home[0] != L'\0';
    }
    fclose(fp);
    return 0;
}

static int python_probe_ok(const wchar_t *pythonw, const wchar_t *cwd) {
    wchar_t cmdline[512];
    DWORD code = 1;

    if (!path_exists(pythonw))
        return 0;
    swprintf_s(cmdline, sizeof(cmdline) / sizeof(cmdline[0]), L"\"%s\" -c \"import sys\"", pythonw);
    if (!run_process(pythonw, cmdline, cwd, &code))
        return 0;
    return code == 0;
}

static int write_venv_check_log(const wchar_t *root, const wchar_t *reason) {
    wchar_t log_file[MAX_PATH * 2];
    SYSTEMTIME st;
    FILE *fp = NULL;

    if (!PathCombineW(log_file, root, L"venv-check.log"))
        return 0;
    GetLocalTime(&st);
    if (_wfopen_s(&fp, log_file, L"a, ccs=UTF-8") != 0 || fp == NULL)
        return 0;
    fwprintf(fp,
             L"[%04u-%02u-%02u %02u:%02u:%02u] venv not usable: %s\n",
             (unsigned)st.wYear,
             (unsigned)st.wMonth,
             (unsigned)st.wDay,
             (unsigned)st.wHour,
             (unsigned)st.wMinute,
             (unsigned)st.wSecond,
             reason);
    fclose(fp);
    return 1;
}

static int venv_usable(const wchar_t *root, const wchar_t **fail_reason) {
    wchar_t pythonw[MAX_PATH * 2];
    wchar_t home[MAX_PATH * 2];

    if (fail_reason)
        *fail_reason = NULL;
    if (!PathCombineW(pythonw, root, L".venv\\Scripts\\pythonw.exe")) {
        if (fail_reason)
            *fail_reason = L"cannot resolve .venv\\Scripts\\pythonw.exe path";
        return 0;
    }
    if (!path_exists(pythonw)) {
        if (fail_reason)
            *fail_reason = L"missing .venv\\Scripts\\pythonw.exe";
        return 0;
    }
    if (read_pyvenv_home(root, home, sizeof(home) / sizeof(home[0]))) {
        if (path_is_directory(home) && path_is_prefix_of(root, home))
            return 1;
        if (fail_reason)
            *fail_reason = L"pyvenv.cfg home missing, not under install root, or invalid";
        return 0;
    }
    if (!python_probe_ok(pythonw, root)) {
        if (fail_reason)
            *fail_reason = L"python probe failed (import sys)";
        return 0;
    }
    return 1;
}

typedef struct SplashStrings {
    const wchar_t *badge;
    const wchar_t *starting;
    const wchar_t *preparing;
} SplashStrings;

static const SplashStrings SPLASH_STRINGS_RU = {
    L"Десктоп",
    L"Запуск Slysh!…",
    L"Подготовка окружения…",
};
static const SplashStrings SPLASH_STRINGS_EN = {
    L"Desktop",
    L"Starting Slysh!…",
    L"Preparing environment…",
};

static int g_splash_locale_en = 0;

static const SplashStrings *splash_strings(void) {
    return g_splash_locale_en ? &SPLASH_STRINGS_EN : &SPLASH_STRINGS_RU;
}

/* Returns 1=en, 2=ru, 0=not found */
static int parse_settings_ui_locale(const wchar_t *settings_path) {
    char buf[65536];
    FILE *fp = NULL;
    size_t n;
    char *p;
    char *value;

    if (!path_exists(settings_path))
        return 0;
    if (_wfopen_s(&fp, settings_path, L"rb") != 0 || fp == NULL)
        return 0;
    n = fread(buf, 1, sizeof(buf) - 1, fp);
    fclose(fp);
    if (n == 0)
        return 0;
    buf[n] = '\0';
    p = strstr(buf, "ui_locale");
    if (p == NULL)
        return 0;
    p = strchr(p, ':');
    if (p == NULL)
        return 0;
    value = p + 1;
    while (*value == ' ' || *value == '\t' || *value == '"')
        value++;
    if (_strnicmp(value, "en", 2) == 0)
        return 1;
    if (_strnicmp(value, "ru", 2) == 0)
        return 2;
    return 0;
}

static int read_install_ui_locale_seed(const wchar_t *install_root) {
    wchar_t seed_path[MAX_PATH * 2];
    char seed[32];
    FILE *fp = NULL;
    size_t n;
    size_t i;

    if (!PathCombineW(seed_path, install_root, L".install-ui-locale"))
        return 0;
    if (!path_exists(seed_path))
        return 0;
    if (_wfopen_s(&fp, seed_path, L"rb") != 0 || fp == NULL)
        return 0;
    n = fread(seed, 1, sizeof(seed) - 1, fp);
    fclose(fp);
    if (n == 0)
        return 0;
    seed[n] = '\0';
    for (i = 0; i < n; i++) {
        if (seed[i] == '\r' || seed[i] == '\n' || seed[i] == ' ' || seed[i] == '\t') {
            seed[i] = '\0';
            break;
        }
    }
    return _stricmp(seed, "en") == 0 ? 1 : 2;
}

static int install_ui_locale_seed_pending(const wchar_t *install_root) {
    wchar_t seed_path[MAX_PATH * 2];

    if (!PathCombineW(seed_path, install_root, L".install-ui-locale"))
        return 0;
    return path_exists(seed_path);
}

static void init_splash_ui_locale(const wchar_t *install_root) {
    wchar_t app_home[MAX_PATH * 2];
    wchar_t settings_path[MAX_PATH * 2];
    DWORD env_len;
    int loc = 0;

    env_len = GetEnvironmentVariableW(
        L"GIGAAM_DESKTOP_HOME", app_home, (DWORD)(sizeof(app_home) / sizeof(app_home[0])));
    if (env_len > 0 && env_len < sizeof(app_home) / sizeof(app_home[0])) {
        if (!PathCombineW(settings_path, app_home, L"settings.json"))
            settings_path[0] = L'\0';
    } else {
        wchar_t local_app[MAX_PATH];
        if (SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, local_app) != S_OK) {
            settings_path[0] = L'\0';
        } else if (!PathCombineW(app_home, local_app, L"Slysh") ||
                   !PathCombineW(settings_path, app_home, L"settings.json")) {
            settings_path[0] = L'\0';
        }
    }

    loc = read_install_ui_locale_seed(install_root);
    if (loc == 0 && settings_path[0] != L'\0')
        loc = parse_settings_ui_locale(settings_path);
    if (loc == 0)
        loc = 2;

    g_splash_locale_en = (loc == 1) ? 1 : 0;
}

static HWND g_splash_hwnd = NULL;
static HICON g_splash_icon = NULL;
static int g_splash_class_registered = 0;
static HFONT g_splash_font_title = NULL;
static HFONT g_splash_font_badge = NULL;
static HFONT g_splash_font_sub = NULL;
static UINT_PTR g_splash_timer = 0;
static DWORD g_wave_tick = 0;
static wchar_t g_splash_status[256];

static void splash_set_status(const wchar_t *subtitle) {
    if (subtitle != NULL && subtitle[0] != L'\0') {
        wcsncpy_s(g_splash_status, sizeof(g_splash_status) / sizeof(g_splash_status[0]), subtitle, _TRUNCATE);
    } else {
        wcscpy_s(
            g_splash_status,
            sizeof(g_splash_status) / sizeof(g_splash_status[0]),
            splash_strings()->starting);
    }
}

static void splash_apply_round_shape(HWND hwnd, int width, int height) {
    HRGN rgn = CreateRoundRectRgn(0, 0, width + 1, height + 1, 32, 32);
    if (rgn != NULL) {
        SetWindowRgn(hwnd, rgn, TRUE);
    }
}

static void splash_fill_round_rect(HDC hdc, const RECT *rc, int radius, COLORREF fill, COLORREF border) {
    HBRUSH brush = CreateSolidBrush(fill);
    HPEN pen = CreatePen(PS_SOLID, 1, border);
    HPEN oldPen = (HPEN)SelectObject(hdc, pen);
    HBRUSH oldBrush = (HBRUSH)SelectObject(hdc, brush);
    RoundRect(hdc, rc->left, rc->top, rc->right, rc->bottom, radius, radius);
    SelectObject(hdc, oldPen);
    SelectObject(hdc, oldBrush);
    DeleteObject(brush);
    DeleteObject(pen);
}

static void splash_draw_wave_bars(HDC hdc, int mid_y, DWORD tick) {
    COLORREF bar_colors[6] = {
        RGB(37, 99, 235), RGB(99, 102, 241), RGB(96, 165, 250),
        RGB(56, 189, 248), RGB(79, 70, 229), RGB(59, 130, 246)};
    static const double phases[6] = {0.0, 1.2, 2.4, 0.7, 1.9, 3.1};
    static const int base_h[6] = {8, 14, 11, 16, 13, 9};
    int bar_x = 0;
    int i;

    for (i = 0; i < 6; i++) {
        double val = sin((tick * 0.18) + phases[i]);
        int h = (int)(base_h[i] + val * 5.0);
        RECT bar;

        if (h < 4)
            h = 4;
        if (h > 18)
            h = 18;
        bar.left = bar_x;
        bar.right = bar_x + 3;
        bar.top = mid_y - h / 2;
        bar.bottom = mid_y + h / 2;
        splash_fill_round_rect(hdc, &bar, 2, bar_colors[i], bar_colors[i]);
        bar_x += 10;
    }
}

static void splash_draw_progress(HDC hdc, const RECT *rcClient, DWORD tick) {
    RECT track = {20, rcClient->bottom - 22, rcClient->right - 20, rcClient->bottom - 16};
    int track_w = track.right - track.left;
    int bar_w;
    int bar_x;
    double phase;
    RECT bar;
    HRGN clip;
    HBRUSH barBrush;

    splash_fill_round_rect(hdc, &track, 6, RGB(241, 245, 249), RGB(241, 245, 249));

    if (track_w <= 0)
        return;
    bar_w = (track_w * 2) / 5;
    if (bar_w < 24)
        bar_w = 24;
    phase = (tick % 90) / 90.0;
    bar_x = track.left + (int)((track_w + bar_w) * phase) - bar_w;

    bar.left = bar_x;
    bar.right = bar_x + bar_w;
    bar.top = track.top;
    bar.bottom = track.bottom;

    clip = CreateRectRgn(track.left, track.top, track.right, track.bottom);
    if (clip != NULL) {
        SelectClipRgn(hdc, clip);
        DeleteObject(clip);
    }
    barBrush = CreateSolidBrush(RGB(37, 99, 235));
    {
        RECT bar2 = bar;
        bar2.right = bar.left + bar_w / 2;
        FillRect(hdc, &bar2, barBrush);
        DeleteObject(barBrush);
        barBrush = CreateSolidBrush(RGB(99, 102, 241));
        bar2.left = bar.left + bar_w / 2;
        bar2.right = bar.right;
        FillRect(hdc, &bar2, barBrush);
        DeleteObject(barBrush);
    }
    SelectClipRgn(hdc, NULL);
}

static void splash_paint_content(HDC hdc, const RECT *rcClient) {
    RECT rcIconBox = {20, 18, 68, 66};
    RECT rcBadge;
    RECT rcWavePill;
    RECT rcTitle = {84, 20, rcClient->right - 88, 42};
    RECT rcSub = {84, 44, rcClient->right - 20, 64};
    SIZE titleSize = {0, 0};
    SIZE badgeSize = {0, 0};
    const wchar_t *badge_text = splash_strings()->badge;
    int badge_len;
    HFONT oldFont;

    splash_fill_round_rect(hdc, rcClient, 32, RGB(255, 255, 255), RGB(226, 232, 240));
    splash_fill_round_rect(hdc, &rcIconBox, 12, RGB(248, 250, 252), RGB(241, 245, 249));
    if (g_splash_icon != NULL) {
        DrawIconEx(hdc, 28, 26, g_splash_icon, 32, 32, 0, NULL, DI_NORMAL);
    }

    SetBkMode(hdc, TRANSPARENT);
    SetTextColor(hdc, RGB(15, 23, 42));
    oldFont = (HFONT)SelectObject(hdc, g_splash_font_title);
    DrawTextW(hdc, L"Slysh!", -1, &rcTitle, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
    GetTextExtentPoint32W(hdc, L"Slysh!", 6, &titleSize);
    SelectObject(hdc, oldFont);

    oldFont = (HFONT)SelectObject(hdc, g_splash_font_badge);
    badge_len = (int)wcslen(badge_text);
    GetTextExtentPoint32W(hdc, badge_text, badge_len, &badgeSize);
    SelectObject(hdc, oldFont);

    rcBadge.left = rcTitle.left + titleSize.cx + 8;
    rcBadge.top = 23;
    rcBadge.right = rcBadge.left + badgeSize.cx + 16;
    if (rcBadge.right - rcBadge.left < 48)
        rcBadge.right = rcBadge.left + 48;
    rcBadge.bottom = 41;
    splash_fill_round_rect(hdc, &rcBadge, 6, RGB(239, 246, 255), RGB(191, 219, 254));
    SetTextColor(hdc, RGB(29, 78, 216));
    oldFont = (HFONT)SelectObject(hdc, g_splash_font_badge);
    DrawTextW(hdc, badge_text, badge_len, &rcBadge, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
    SelectObject(hdc, oldFont);

    rcWavePill.left = rcClient->right - 88;
    rcWavePill.top = 20;
    rcWavePill.right = rcClient->right - 20;
    rcWavePill.bottom = 44;
    splash_fill_round_rect(hdc, &rcWavePill, 8, RGB(239, 246, 255), RGB(219, 234, 254));
    {
        int save = SaveDC(hdc);
        SetViewportOrgEx(hdc, rcWavePill.left + 10, 0, NULL);
        splash_draw_wave_bars(hdc, 32, g_wave_tick);
        RestoreDC(hdc, save);
    }

    SetTextColor(hdc, RGB(100, 116, 139));
    oldFont = (HFONT)SelectObject(hdc, g_splash_font_sub);
    DrawTextW(hdc, g_splash_status, -1, &rcSub, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX);
    SelectObject(hdc, oldFont);

    splash_draw_progress(hdc, rcClient, g_wave_tick);
}

static void splash_pump_messages(void) {
    MSG msg;

    while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
}

static LRESULT CALLBACK splash_wnd_proc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_ERASEBKGND:
        return 1;
    case WM_TIMER:
        g_wave_tick++;
        InvalidateRect(hwnd, NULL, FALSE);
        return 0;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC hdcScreen = BeginPaint(hwnd, &ps);
        RECT rc;
        HDC hdc;
        HBITMAP memBmp;
        HBITMAP oldBmp;

        GetClientRect(hwnd, &rc);
        hdc = CreateCompatibleDC(hdcScreen);
        memBmp = CreateCompatibleBitmap(hdcScreen, rc.right, rc.bottom);
        oldBmp = (HBITMAP)SelectObject(hdc, memBmp);
        splash_paint_content(hdc, &rc);
        BitBlt(hdcScreen, 0, 0, rc.right, rc.bottom, hdc, 0, 0, SRCCOPY);
        SelectObject(hdc, oldBmp);
        DeleteObject(memBmp);
        DeleteDC(hdc);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_DESTROY:
        if (g_splash_timer != 0) {
            KillTimer(hwnd, g_splash_timer);
            g_splash_timer = 0;
        }
        g_splash_hwnd = NULL;
        if (g_splash_icon != NULL) {
            DestroyIcon(g_splash_icon);
            g_splash_icon = NULL;
        }
        return 0;
    default:
        return DefWindowProcW(hwnd, msg, wParam, lParam);
    }
}

static void splash_show(const wchar_t *root, const wchar_t *subtitle) {
    WNDCLASSW wc;
    wchar_t title[128];
    wchar_t icon_path[MAX_PATH * 2];
    RECT desk;
    HINSTANCE inst = GetModuleHandleW(NULL);
    int w = 400;
    int h = 116;
    int x;
    int y;

    splash_set_status(subtitle);
    if (g_splash_hwnd != NULL) {
        InvalidateRect(g_splash_hwnd, NULL, FALSE);
        splash_pump_messages();
        return;
    }
    if (PathCombineW(icon_path, root, L"slysh.ico") && path_exists(icon_path)) {
        g_splash_icon = (HICON)LoadImageW(
            NULL, icon_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE | LR_DEFAULTSIZE);
    } else {
        g_splash_icon = LoadIconW(NULL, IDI_APPLICATION);
    }
    if (!g_splash_class_registered) {
        ZeroMemory(&wc, sizeof(wc));
        wc.lpfnWndProc = splash_wnd_proc;
        wc.hInstance = inst;
        wc.hCursor = LoadCursorW(NULL, IDC_APPSTARTING);
        wc.hbrBackground = (HBRUSH)GetStockObject(WHITE_BRUSH);
        wc.style = CS_DROPSHADOW | CS_HREDRAW | CS_VREDRAW;
        wc.lpszClassName = L"SlyshSplashWnd";
        RegisterClassW(&wc);
        g_splash_class_registered = 1;
    }
    if (g_splash_font_title == NULL) {
        g_splash_font_title = CreateFontW(
            -16, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    }
    if (g_splash_font_badge == NULL) {
        g_splash_font_badge = CreateFontW(
            -10, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    }
    if (g_splash_font_sub == NULL) {
        g_splash_font_sub = CreateFontW(
            -12, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    }
    swprintf_s(title, sizeof(title) / sizeof(title[0]), L"Slysh!");
    if (GetWindowRect(GetDesktopWindow(), &desk)) {
        x = desk.left + (desk.right - desk.left - w) / 2;
        y = desk.top + (desk.bottom - desk.top - h) / 2;
    } else {
        x = 200;
        y = 200;
    }
    g_splash_hwnd = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        L"SlyshSplashWnd",
        title,
        WS_POPUP | WS_VISIBLE,
        x,
        y,
        w,
        h,
        NULL,
        NULL,
        inst,
        NULL);
    if (g_splash_hwnd == NULL)
        return;
    {
        DWORD corner_pref = DWMWCP_ROUND;
        DwmSetWindowAttribute(
            g_splash_hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, &corner_pref, sizeof(corner_pref));
    }
    splash_apply_round_shape(g_splash_hwnd, w, h);
    g_splash_timer = SetTimer(g_splash_hwnd, 1, 40, NULL);
    ShowWindow(g_splash_hwnd, SW_SHOW);
    UpdateWindow(g_splash_hwnd);
    splash_pump_messages();
}

static void splash_hide(void) {
    if (g_splash_hwnd != NULL) {
        if (g_splash_timer != 0) {
            KillTimer(g_splash_hwnd, g_splash_timer);
            g_splash_timer = 0;
        }
        DestroyWindow(g_splash_hwnd);
        g_splash_hwnd = NULL;
    }
}

static int remove_venv_dir(const wchar_t *root) {
    wchar_t venv[MAX_PATH * 2];
    wchar_t from[(MAX_PATH * 2) + 2];
    SHFILEOPSTRUCTW op;

    if (!PathCombineW(venv, root, L".venv"))
        return 0;
    if (!path_is_directory(venv))
        return 1;
    if (wcslen(venv) + 2 >= sizeof(from) / sizeof(from[0]))
        return 0;
    wcscpy_s(from, sizeof(from) / sizeof(from[0]), venv);
    from[wcslen(from) + 1] = L'\0';

    ZeroMemory(&op, sizeof(op));
    op.wFunc = FO_DELETE;
    op.pFrom = from;
    op.fFlags = FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI;
    if (SHFileOperationW(&op) != 0)
        return 0;
    return !path_is_directory(venv);
}

static int wheelhouse_has_wheels(const wchar_t *root) {
    wchar_t dir[MAX_PATH * 2];
    wchar_t pattern[MAX_PATH * 2];
    WIN32_FIND_DATAW fd;
    HANDLE h;

    if (!PathCombineW(dir, root, L"wheelhouse"))
        return 0;
    if (!path_is_directory(dir))
        return 0;
    if (swprintf_s(pattern, sizeof(pattern) / sizeof(pattern[0]), L"%ls\\*.whl", dir) < 0)
        return 0;
    h = FindFirstFileW(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    FindClose(h);
    return 1;
}

static int wheelhouse_has_requirements_ui(const wchar_t *root) {
    wchar_t req[MAX_PATH * 2];

    if (!PathCombineW(req, root, L"wheelhouse\\requirements-ui.txt"))
        return 0;
    return path_exists(req);
}

static void trim_stamp_text(char *text) {
    size_t len;
    size_t start = 0;
    size_t end;

    if (text == NULL)
        return;
    while (text[start] == ' ' || text[start] == '\t' || text[start] == '\r' || text[start] == '\n')
        start++;
    if (text[start] == '\0') {
        text[0] = '\0';
        return;
    }
    len = strlen(text + start);
    end = start + len;
    while (end > start &&
           (text[end - 1] == ' ' || text[end - 1] == '\t' || text[end - 1] == '\r' || text[end - 1] == '\n')) {
        end--;
    }
    if (start > 0)
        memmove(text, text + start, end - start);
    text[end - start] = '\0';
}

static int read_install_stamp_file(const wchar_t *path, char *buf, size_t buf_size) {
    FILE *fp = NULL;
    size_t n;

    if (buf == NULL || buf_size < 2)
        return 0;
    buf[0] = '\0';
    if (path == NULL || !path_exists(path))
        return 0;
    if (_wfopen_s(&fp, path, L"rb") != 0 || fp == NULL)
        return 0;
    n = fread(buf, 1, buf_size - 1, fp);
    fclose(fp);
    if (n == 0)
        return 0;
    buf[n] = '\0';
    trim_stamp_text(buf);
    return buf[0] != '\0';
}

static int payload_sync_pending_file(const wchar_t *root) {
    wchar_t path[MAX_PATH * 2];

    if (!PathCombineW(path, root, L".payload-sync-pending"))
        return 0;
    return path_exists(path);
}

static int payload_venv_resync_needed(const wchar_t *root) {
    wchar_t path[MAX_PATH * 2];
    char build[96];
    char stamp[96];

    if (install_ui_locale_seed_pending(root))
        return 1;
    if (payload_sync_pending_file(root))
        return 1;
    if (!PathCombineW(path, root, L"payload-build.txt") || !path_exists(path))
        return 0;
    if (!read_install_stamp_file(path, build, sizeof(build)))
        return 0;
    if (!PathCombineW(path, root, L".venv-payload-sync") || !path_exists(path))
        return 1;
    if (!read_install_stamp_file(path, stamp, sizeof(stamp)))
        return 1;
    return _stricmp(build, stamp) != 0;
}

static int write_venv_payload_sync_stamp(const wchar_t *root) {
    wchar_t src[MAX_PATH * 2];
    wchar_t dst[MAX_PATH * 2];

    if (!PathCombineW(src, root, L"payload-build.txt") || !path_exists(src))
        return 1;
    if (!PathCombineW(dst, root, L".venv-payload-sync"))
        return 0;
    if (!CopyFileW(src, dst, FALSE))
        return 0;
    if (PathCombineW(dst, root, L".payload-sync-pending") && path_exists(dst))
        DeleteFileW(dst);
    return 1;
}

static int find_bundled_python(const wchar_t *root, wchar_t *python, size_t python_chars) {
    wchar_t rt[MAX_PATH * 2];
    wchar_t pattern[MAX_PATH * 2];
    WIN32_FIND_DATAW fd;
    HANDLE h;

    python[0] = L'\0';
    if (!PathCombineW(rt, root, L"runtime\\python"))
        return 0;
    if (!path_is_directory(rt))
        return 0;
    if (swprintf_s(pattern, sizeof(pattern) / sizeof(pattern[0]), L"%ls\\cpython-*", rt) < 0)
        return 0;
    h = FindFirstFileW(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    do {
        if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) == 0)
            continue;
        if (wcscmp(fd.cFileName, L".") == 0 || wcscmp(fd.cFileName, L"..") == 0)
            continue;
        if (!PathCombineW(python, rt, fd.cFileName))
            continue;
        if (!PathAppendW(python, L"python.exe"))
            continue;
        if (path_exists(python)) {
            FindClose(h);
            return 1;
        }
        python[0] = L'\0';
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    return 0;
}

static int run_uv_pip_sync_only(const wchar_t *root, DWORD *exit_code, int reinstall_slysh) {
    wchar_t uv[MAX_PATH * 2];
    wchar_t wheelhouse[MAX_PATH * 2];
    wchar_t venv_py[MAX_PATH * 2];
    wchar_t req_ui[MAX_PATH * 2];
    wchar_t cmdline[4096];

    if (!PathCombineW(uv, root, L"bin\\uv.exe") || !path_exists(uv))
        return 0;
    if (!wheelhouse_has_requirements_ui(root) || !wheelhouse_has_wheels(root))
        return 0;
    if (!PathCombineW(wheelhouse, root, L"wheelhouse"))
        return 0;
    if (!PathCombineW(req_ui, root, L"wheelhouse\\requirements-ui.txt"))
        return 0;
    if (!PathCombineW(venv_py, root, L".venv\\Scripts\\python.exe") || !path_exists(venv_py))
        return 0;
    if (reinstall_slysh) {
        swprintf_s(cmdline,
                   sizeof(cmdline) / sizeof(cmdline[0]),
                   L"\"%ls\" pip sync --python \"%ls\" --no-index --find-links \"%ls\" "
                   L"--reinstall-package slysh \"%ls\"",
                   uv,
                   venv_py,
                   wheelhouse,
                   req_ui);
    } else {
        swprintf_s(cmdline,
                   sizeof(cmdline) / sizeof(cmdline[0]),
                   L"\"%ls\" pip sync --python \"%ls\" --no-index --find-links \"%ls\" \"%ls\"",
                   uv,
                   venv_py,
                   wheelhouse,
                   req_ui);
    }
    return run_process_wait(uv, cmdline, root, exit_code, 1);
}

static int run_uv_sync(const wchar_t *root, DWORD *exit_code) {
    wchar_t uv[MAX_PATH * 2];
    wchar_t wheelhouse[MAX_PATH * 2];
    wchar_t venv_py[MAX_PATH * 2];
    wchar_t req_ui[MAX_PATH * 2];
    wchar_t venv_dir[MAX_PATH * 2];
    wchar_t bundled_py[MAX_PATH * 2];
    wchar_t cmdline[4096];

    if (!PathCombineW(uv, root, L"bin\\uv.exe") || !path_exists(uv))
        return 0;
    if (wheelhouse_has_requirements_ui(root) && wheelhouse_has_wheels(root)) {
        if (!PathCombineW(wheelhouse, root, L"wheelhouse"))
            return 0;
        if (!PathCombineW(req_ui, root, L"wheelhouse\\requirements-ui.txt"))
            return 0;
        if (!PathCombineW(venv_dir, root, L".venv"))
            return 0;
        if (!PathCombineW(venv_py, root, L".venv\\Scripts\\python.exe"))
            return 0;
        if (!find_bundled_python(root, bundled_py, sizeof(bundled_py) / sizeof(bundled_py[0]))) {
            *exit_code = 127;
            return 0;
        }
        swprintf_s(cmdline,
                   sizeof(cmdline) / sizeof(cmdline[0]),
                   L"\"%ls\" venv \"%ls\" --python \"%ls\"",
                   uv,
                   venv_dir,
                   bundled_py);
        if (!run_process_wait(uv, cmdline, root, exit_code, 1) || *exit_code != 0)
            return 1;
        swprintf_s(cmdline,
                   sizeof(cmdline) / sizeof(cmdline[0]),
                   L"\"%ls\" pip sync --python \"%ls\" --no-index --find-links \"%ls\" \"%ls\"",
                   uv,
                   venv_py,
                   wheelhouse,
                   req_ui);
        return run_process_wait(uv, cmdline, root, exit_code, 1);
    }
    if (wheelhouse_has_wheels(root)) {
        if (!PathCombineW(wheelhouse, root, L"wheelhouse"))
            return 0;
        swprintf_s(cmdline,
                   sizeof(cmdline) / sizeof(cmdline[0]),
                   L"\"%ls\" sync --no-editable --no-dev --find-links \"%ls\" --offline",
                   uv,
                   wheelhouse);
    } else {
        swprintf_s(cmdline, sizeof(cmdline) / sizeof(cmdline[0]), L"\"%ls\" sync", uv);
    }
    return run_process_wait(uv, cmdline, root, exit_code, 1);
}

static int write_venv_repair_error(const wchar_t *root, DWORD sync_code, int retried, const wchar_t *phase) {
    wchar_t err_file[MAX_PATH * 2];
    SYSTEMTIME st;
    FILE *fp = NULL;

    if (!PathCombineW(err_file, root, L"launch-last-error.txt"))
        return 0;
    GetLocalTime(&st);
    if (_wfopen_s(&fp, err_file, L"a, ccs=UTF-8") != 0 || fp == NULL)
        return 0;
    fwprintf(fp,
             L"[%04u-%02u-%02u %02u:%02u:%02u] venv repair: %ls exit %lu%s\n",
             (unsigned)st.wYear,
             (unsigned)st.wMonth,
             (unsigned)st.wDay,
             (unsigned)st.wHour,
             (unsigned)st.wMinute,
             (unsigned)st.wSecond,
             phase != NULL ? phase : L"uv",
             (unsigned long)sync_code,
             retried ? L" (after removing .venv)" : L"");
    fclose(fp);
    return 1;
}

static int ensure_venv(const wchar_t *root) {
    wchar_t venv_dir[MAX_PATH * 2];
    DWORD code = 0;
    const wchar_t *fail_reason = NULL;

    if (!set_install_uv_env(root))
        return 0;

    if (venv_usable(root, &fail_reason))
        return 1;

    write_venv_check_log(root, fail_reason != NULL ? fail_reason : L"unknown");

    splash_show(root, splash_strings()->preparing);

    if (!PathCombineW(venv_dir, root, L"bin\\uv.exe") || !path_exists(venv_dir)) {
        splash_hide();
        show_error(L"Slysh!",
                   L"Не найдено окружение Python (.venv).\n"
                   L"Переустановите Slysh или запустите Slysh.bat из папки программы.");
        return 0;
    }

    if (PathCombineW(venv_dir, root, L".venv") && path_is_directory(venv_dir)) {
        if (!remove_venv_dir(root)) {
            splash_hide();
            show_error(L"Slysh!",
                       L"Не удалось сбросить повреждённое окружение (.venv).\n"
                       L"Закройте Slysh и удалите папку .venv вручную.");
            return 0;
        }
    }

    if (!run_uv_sync(root, &code) || code != 0) {
        splash_hide();
        write_venv_repair_error(
            root,
            code,
            0,
            wheelhouse_has_requirements_ui(root) ? L"uv venv or pip sync" : L"uv sync");
        if (wheelhouse_has_wheels(root)) {
            show_error(L"Slysh!",
                       L"Не удалось восстановить окружение из локального wheelhouse.\n"
                       L"Переустановите Slysh или запустите Slysh.bat из папки программы.");
        } else {
            show_error(L"Slysh!",
                       L"Не удалось восстановить окружение (uv sync).\n"
                       L"Проверьте интернет и переустановите Slysh.");
        }
        return 0;
    }

    if (!venv_usable(root, &fail_reason)) {
        splash_hide();
        if (fail_reason != NULL) {
            write_venv_check_log(root, fail_reason);
        }
        show_error(L"Slysh!",
                   L"Окружение Python установлено, но не запускается.\n"
                   L"Переустановите Slysh.");
        return 0;
    }
    if (write_venv_payload_sync_stamp(root))
        (void)0;
    splash_hide();
    return 1;
}

static int ensure_payload_venv_sync(const wchar_t *root) {
    DWORD code = 0;
    const wchar_t *fail_reason = NULL;
    int reinstall_slysh;

    if (!payload_venv_resync_needed(root))
        return 1;
    if (!venv_usable(root, &fail_reason))
        return 1;
    if (!set_install_uv_env(root))
        return 0;

    reinstall_slysh = 1;
    splash_show(root, splash_strings()->preparing);
    if (!run_uv_pip_sync_only(root, &code, reinstall_slysh) || code != 0) {
        splash_hide();
        write_venv_repair_error(root, code, 0, L"payload pip sync");
        show_error(L"Slysh!",
                   L"Не удалось обновить окружение после установки.\n"
                   L"Переустановите Slysh или удалите папку .venv и запустите снова.");
        return 0;
    }
    if (!write_venv_payload_sync_stamp(root)) {
        splash_hide();
        show_error(L"Slysh!",
                   L"Не удалось записать метку синхронизации окружения.\n"
                   L"Проверьте права на папку программы.");
        return 0;
    }
    splash_hide();
    return 1;
}

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, PWSTR lpCmdLine, int nCmdShow) {
    wchar_t exe_path[MAX_PATH];
    wchar_t root[MAX_PATH];
    wchar_t models[MAX_PATH * 2];
    wchar_t hf_home[MAX_PATH * 2];
    wchar_t hf_hub[MAX_PATH * 2];
    wchar_t pythonw[MAX_PATH * 2];
    wchar_t cmdline[512];
    DWORD code = 0;
    (void)hInstance;
    (void)hPrevInstance;
    (void)lpCmdLine;
    (void)nCmdShow;

    if (GetModuleFileNameW(NULL, exe_path, MAX_PATH) == 0) {
        show_error(L"Slysh!", L"Не удалось определить путь к программе.");
        return 1;
    }
    wcscpy_s(root, MAX_PATH, exe_path);
    if (!PathRemoveFileSpecW(root)) {
        show_error(L"Slysh!", L"Не удалось определить папку программы.");
        return 1;
    }

    SetEnvironmentVariableW(L"NO_PROXY", L"");
    SetEnvironmentVariableW(L"no_proxy", L"");

    clear_dev_python_env();

    if (!set_env_pair(L"SLYSH_INSTALL_ROOT", root))
        goto env_fail;
    if (!PathCombineW(models, root, L"models"))
        goto env_fail;
    if (!set_env_pair(L"GIGAAM_MODEL_ROOT", models))
        goto env_fail;
    if (!set_env_pair(L"GIGAAM_PROJECT_MODELS", models))
        goto env_fail;
    if (!PathCombineW(hf_home, models, L"huggingface"))
        goto env_fail;
    if (!set_env_pair(L"HF_HOME", hf_home))
        goto env_fail;
    if (!PathCombineW(hf_hub, hf_home, L"hub"))
        goto env_fail;
    if (!set_env_pair(L"HUGGINGFACE_HUB_CACHE", hf_hub))
        goto env_fail;
    if (!set_env_pair(L"GIGAAM_DIARIZATION_PATH", L""))
        goto env_fail;
    if (!set_env_pair(L"GIGAAM_UI_AUTH", L"1"))
        goto env_fail;
    if (!set_env_pair(L"GIGAAM_LOOPBACK_STRICT", L"1"))
        goto env_fail;
    if (!set_env_pair(L"SLYSH_DISABLE_OPENAPI", L"1"))
        goto env_fail;
    if (!set_env_pair(L"GIGAAM_UI_BOOTSTRAP_HTML", L"0"))
        goto env_fail;
    if (!prepend_path_bin(root))
        goto env_fail;

    if (!SetCurrentDirectoryW(root)) {
        show_error(L"Slysh!", L"Не найдена папка программы.");
        return 1;
    }

    init_splash_ui_locale(root);
    splash_set_status(NULL);

    if (!ensure_venv(root))
        return 1;

    if (!ensure_payload_venv_sync(root))
        return 1;

    if (!PathCombineW(pythonw, root, L".venv\\Scripts\\pythonw.exe")) {
        show_error(L"Slysh!", L"Не найден pythonw.exe.");
        return 1;
    }

    swprintf_s(cmdline, sizeof(cmdline) / sizeof(cmdline[0]), L"\"%s\" -m slysh.app", pythonw);
    splash_show(root, NULL);
    {
        int launched = run_process_launch(pythonw, cmdline, root, &code);
        if (launched == 0) {
            splash_hide();
            show_error(L"Slysh!", L"Не удалось запустить Slysh.");
            return 1;
        }
        if (launched == 2 && code != 0) {
            splash_hide();
            write_launch_error(root, code);
            show_app_exit_error(code);
            return (int)code;
        }
    }
    splash_hide();
    return 0;

env_fail:
    show_error(L"Slysh!", L"Не удалось настроить окружение.");
    return 1;
}
