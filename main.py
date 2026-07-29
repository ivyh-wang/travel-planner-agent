"""旅游攻略 Agent —— 命令行入口。

子命令：
    collect   采集一条帖子/视频链接（或 --text 直接粘贴），提取推荐并入库
    guide     生成某城市攻略（自动采用采集库）
    library   查看/搜索/删除采集库条目

通用参数：--provider / --model 可覆盖 .env 中的 provider 与模型。
"""

import argparse
import sys

from .collect import extractor, fetcher, library as library_mod
from .guide import generator
from .llm import LLMClient, LLMError
from .prompts import planner_prompt


def _client(args) -> LLMClient:
    return LLMClient(provider=getattr(args, "provider", None), model=getattr(args, "model", None))


def cmd_collect(args) -> int:
    client = _client(args)
    if args.text:
        text = args.text
        source_url = "（用户直接粘贴）"
    else:
        print(f"正在抓取：{args.url}")
        text, err = fetcher.fetch(args.url)
        source_url = args.url
        if text is None:
            print(f"警告：{err}")
            print("可改用 --text 直接粘贴帖子正文/视频字幕文本。")
            return 1

    print(f"已抓取内容（{len(text)} 字），正在用 LLM 提取推荐……")
    try:
        items = extractor.extract_items(text, source_url, client)
    except LLMError as exc:
        print(f"错误：{exc}")
        return 1

    if not items:
        print("未提取到推荐条目。")
        return 0

    print(f"\n提取到 {len(items)} 条推荐，请确认：")
    for i, it in enumerate(items, 1):
        print(
            f"  {i}. [{it['type']}] {it['name']}"
            f"（{it.get('location', '')}）— {it.get('reason', '')}"
            f"  标签:{it.get('tags')}"
        )

    choice = input("\n保存哪些？[a]全部 / [n]取消 / 输入编号如 1,3：").strip().lower()
    if choice in ("", "n"):
        print("已取消。")
        return 0
    if choice == "a":
        selected = items
    else:
        idxs = [int(x) - 1 for x in choice.replace("，", ",").split(",") if x.strip().isdigit()]
        selected = [items[i] for i in idxs if 0 <= i < len(items)]
    if not selected:
        print("没有可保存的条目。")
        return 0

    city = args.city or input("归入哪个城市？：").strip() or "未分类"
    lib = library_mod.Library()
    added = lib.add_items(city, selected)
    print(f"已写入采集库『{city}』，新增 {added} 条。")
    return 0


def cmd_guide(args) -> int:
    client = _client(args)
    lib = library_mod.Library()
    md = generator.generate(args.request, args.city, client, lib)
    if md is None:
        return 1
    path = generator.save_guide(md, args.city, args.request)
    print(f"攻略已生成：{path}")
    return 0


def cmd_library(args) -> int:
    lib = library_mod.Library()
    if args.action == "list":
        cities = lib.list_cities()
        if not cities:
            print("采集库为空。")
        for c, info in cities.items():
            print(f"{c}: {info['count']} 条")
    elif args.action == "show":
        items = lib.get_items(args.city)
        if not items:
            print(f"『{args.city}』暂无条目。")
        for i, it in enumerate(items):
            print(f"  {i}. [{it['type']}] {it['name']} — {it.get('reason', '')}")
    elif args.action == "search":
        res = lib.search(args.query)
        if not res:
            print("未找到匹配。")
        for city, hits in res.items():
            print(f"# {city}")
            for it in hits:
                print(f"  - [{it['type']}] {it['name']}（{it.get('location', '')}）")
    elif args.action == "remove":
        removed = lib.remove_item(args.city, args.index)
        print(f"已删除：{removed}" if removed else "未找到该条目。")
    return 0


def cmd_plan(args) -> int:
    """分阶段、多轮协作的旅行规划专家模式。"""
    client = _client(args)
    lib = library_mod.Library()
    library_md = lib.to_markdown(args.city) if args.city else ""
    system = planner_prompt.build_system(library_md)
    history: list[dict] = []
    first = (
        f"我的初步需求：{args.request}\n"
        "请先完成初始化问候，引导我补充缺失的旅行基础信息，"
        "然后按你的流程进入第一步：整体旅行框架设计。"
    )
    history.append({"role": "user", "content": first})

    print("=" * 60)
    print("进入旅行规划专家模式（分阶段、多轮）。输入「继续」推进下一阶段，")
    print("「完成」输出并保存最终攻略，「退出」结束。")
    print("=" * 60)

    while True:
        try:
            assistant = client.chat(system, history)
        except LLMError as exc:
            print(f"错误：{exc}")
            return 1
        print("\n" + assistant)
        history.append({"role": "assistant", "content": assistant})

        cont = input(
            "\n（补充信息/确认请直接输入；『继续』推进下一阶段；"
            "『完成』输出并保存最终攻略；『退出』结束）: "
        ).strip()

        if cont in ("退出", "quit", "q"):
            print("已退出规划。")
            return 0
        if cont in ("完成", "结束"):
            history.append(
                {
                    "role": "user",
                    "content": (
                        "请基于以上讨论，整理并输出完整的旅行攻略"
                        "（含全部章节：概览、每日行程、美食、预算、地图与交通、"
                        "避坑与贴士、应急预案、检查清单），并优先采用采集库推荐并标注来源。"
                    ),
                }
            )
            try:
                final = client.chat(system, history)
            except LLMError as exc:
                print(f"错误：{exc}")
                return 1
            print("\n" + final)
            path = generator.save_guide(final, args.city, args.request)
            print(f"\n最终攻略已保存：{path}")
            return 0
        history.append(
            {"role": "user", "content": cont or "继续，请进入下一阶段。"}
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="travel-agent",
        description="旅游攻略 Agent：生成攻略 + 采集帖子/视频推荐",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("collect", help="采集帖子/视频链接中的推荐")
    pc.add_argument("url", nargs="?", help="帖子/视频链接")
    pc.add_argument("--text", help="直接粘贴帖子正文/视频字幕文本（跳过抓取）")
    pc.add_argument("--city", help="归入的城市（缺省时交互询问）")
    pc.add_argument("--provider", help="覆盖 provider")
    pc.add_argument("--model", help="覆盖 model")
    pc.set_defaults(func=cmd_collect)

    pg = sub.add_parser("guide", help="生成旅游攻略")
    pg.add_argument("request", help="出行需求，如『东京 5日游，爱吃拉面』")
    pg.add_argument("--city", required=True, help="攻略城市（用于载入采集库）")
    pg.add_argument("--provider", help="覆盖 provider")
    pg.add_argument("--model", help="覆盖 model")
    pg.set_defaults(func=cmd_guide)

    pp = sub.add_parser(
        "plan", help="分阶段、多轮协作的旅行规划专家（推荐）"
    )
    pp.add_argument("request", help="初步需求，如『东京 5日游，爱吃拉面』")
    pp.add_argument("--city", help="攻略城市（用于载入采集库，可选）")
    pp.add_argument("--provider", help="覆盖 provider")
    pp.add_argument("--model", help="覆盖 model")
    pp.set_defaults(func=cmd_plan)

    pl = sub.add_parser("library", help="管理采集库")
    pl.add_argument(
        "action",
        choices=["list", "show", "search", "remove"],
        help="list=列出城市 / show=查看城市 / search=搜索 / remove=删除",
    )
    pl.add_argument("--city", help="城市名（show/remove 用）")
    pl.add_argument("--query", help="搜索关键词（search 用）")
    pl.add_argument("--index", type=int, help="条目序号（remove 用，从 0 开始）")
    pl.set_defaults(func=cmd_library)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "collect" and not args.url and not args.text:
        parser.error("collect 需要提供 url 或 --text")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
