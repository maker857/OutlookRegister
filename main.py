import os
import time
import json
from get_token import get_access_token
from concurrent.futures import ThreadPoolExecutor
from utils import random_email, generate_strong_password
from controllers.ruyipage_controller import RuyipageController
from controllers.camoufox_controller import CamoufoxController
from controllers.patchright_controller import PatchrightController
from controllers.playwright_controller import PlaywrightController



# --- 不确定有无帮助 ---
# 0. 视窗大小
# 1. CDP 检测：wait_for_timeout --> time.sleep()
# 2. 使用 launch_persistent_context 
# 3. 避免短时间访问
# 4. 模拟真人轨迹
# 时区

def process_single_flow(controller):
    page = None

    try:
        page = controller.get_thread_page()

        email = random_email()
        password = generate_strong_password()

        # 调用 controller 特定的注册方法 
        result = controller.outlook_register(page, email, password)

        if result and not controller.enable_oauth2:
            return True
        elif not result:
            return False

        token_result = get_access_token(page, email)
        if token_result[0]:
            refresh_token, access_token, expire_at = token_result
            with open(os.path.join(os.path.dirname(__file__), 'Results', 'secured_tokens.txt'), 'a', encoding='utf-8') as f2:
                f2.write(f"{email}{controller.email_suffix}---{password}---{refresh_token}---{access_token}---{expire_at}---{page.recovery_email}\n") 
            print(f'[Success: TokenAuth] - {email}{controller.email_suffix}')
            return True
        else:
            return False

    except Exception as e:
        print(e)
        return False
    
    finally:

        controller.clean_up(page, "done_browser")

def run_concurrent_flows(controller, concurrent_flows=10, max_tasks=100):
    task_counter = 0
    succeeded_tasks = 0
    failed_tasks = 0

    with ThreadPoolExecutor(max_workers=concurrent_flows) as executor:
        running_futures = set()

        while task_counter < max_tasks or len(running_futures) > 0:
            done_futures = {f for f in running_futures if f.done()}
            for future in done_futures:
                try:
                    if future.result():
                        succeeded_tasks += 1
                    else:
                        failed_tasks += 1
                except Exception as e:
                    failed_tasks += 1
                    print(e)
                running_futures.remove(future)

            while len(running_futures) < concurrent_flows and task_counter < max_tasks:
                new_future = executor.submit(process_single_flow, controller)
                running_futures.add(new_future)
                task_counter += 1
                if max_tasks > 1 and task_counter % (max_tasks // 2) == 0:
                    print(f"已提交 {task_counter}/{max_tasks} 任务.")
                elif max_tasks == 1:
                    print(f"已提交 {task_counter}/{max_tasks} 任务.")

            time.sleep(0.5)

    print(f"\n[Result] - 共: {max_tasks}, 成功 {succeeded_tasks}, 失败 {failed_tasks}")


def check_mail_config(data):
    """
    开跑前先校验辅助邮箱配置。

    不校验的话，流程会一路注册成功，直到最后绑定那步才报
    "Invalid URL '/api/config'" 之类的错 —— 一个干净 IP 和一次成功注册就这么废了，
    而 IP 信誉是这里最贵的资源。
    """
    choice = data.get("choosed_mail")

    if choice == "moemail":
        cfg = data.get("moemail", {})
        missing = [k for k in ("base_url", "apikey") if not str(cfg.get(k, "")).strip()]
        if missing:
            print(f"[Error: Config] - choosed_mail 是 moemail，但 {'、'.join('moemail.' + m for m in missing)} 还没填。")
            print("                  需要自建 moemail 服务后填入其地址与 API Key，或把 choosed_mail 改成 outlookgraph。")
            return False
        if not str(cfg["base_url"]).startswith(("http://", "https://")):
            print(f"[Error: Config] - moemail.base_url 需要带协议头，当前是 {cfg['base_url']!r}。")
            return False
        return True

    if choice == "outlookgraph":
        cfg = data.get("outlookgraph", {})
        if not str(cfg.get("client_id", "")).strip():
            print("[Error: Config] - choosed_mail 是 outlookgraph，但 outlookgraph.client_id 还没填（Azure 应用的 client id）。")
            return False

        strategy = cfg.get("strategy")
        if strategy == "single_email":
            single = cfg.get("single_email", {})
            if not str(single.get("email", "")).strip() or not str(single.get("refresh_token", "")).strip():
                print("[Error: Config] - outlookgraph.single_email 的 email 与 refresh_token 都要填。")
                return False
            return True

        if strategy == "file":
            path = cfg.get("file", {}).get("path", "")
            if not os.path.exists(path):
                print(f"[Error: Config] - 辅助邮箱池文件不存在: {path}")
                return False
            with open(path, "r", encoding="utf-8") as f:
                usable = [l for l in f.read().splitlines() if '@' in l and len(l.split('---')) >= 5]
            if not usable:
                print(f"[Error: Config] - {path} 里没有可用记录，每行格式需为 "
                      f"账号---密码---refresh_token---access_token---expire_at")
                return False
            print(f"[Info: Config] - 辅助邮箱池 {path} 可用记录 {len(usable)} 条。")
            return True

        print(f"[Error: Config] - outlookgraph.strategy 只能是 file 或 single_email，当前是 {strategy!r}。")
        return False

    print(f"[Error: Config] - 不支持的 choosed_mail: {choice!r}，可填 moemail 或 outlookgraph。")
    return False


if __name__ == "__main__":

    with open('config.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    os.makedirs("Results", exist_ok=True)

    max_tasks = data["max_tasks"]
    concurrent_flows = data["concurrent_flows"]

    if not check_mail_config(data):
        raise SystemExit(1)

    if data["choose_browser"] =="patchright":
        selected_controller = PatchrightController()
    elif data["choose_browser"] =="playwright":
        selected_controller = PlaywrightController()
    elif data["choose_browser"] =="ruyipage":
        selected_controller = RuyipageController()   # 成功注册 + Oauth2(~2 ~ 3 MB)
    elif data["choose_browser"] =="camoufox":
        selected_controller = CamoufoxController()   # Playwright 驱动的指纹 Firefox，默认选项
    else:
        print("不支持的浏览器类型，填写camoufox、patchright、playwright或者ruyipage")
        raise SystemExit(1)

    try:
        run_concurrent_flows(selected_controller, concurrent_flows, max_tasks)
    finally:
        selected_controller.clean_up(type="all_browser")