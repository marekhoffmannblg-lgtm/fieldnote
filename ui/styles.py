from __future__ import annotations

import streamlit as st


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root { --ink:#1b292d; --muted:#66767a; --paper:#f5f5f1; --card:#fff; --line:#dce4e1; --teal:#15776d; --amber:#a97124; --red:#af5548; --blue:#426d83; --nav:#112e34; }
        .stApp { background:radial-gradient(circle at 94% 0,rgba(21,119,109,.07),transparent 25rem),var(--paper); color:var(--ink); font-family:"Avenir Next","Segoe UI",sans-serif; }
        .block-container { max-width:1360px; padding:2.2rem clamp(1rem,3vw,3rem) 4rem; }
        h1,h2,h3 { letter-spacing:-.025em; color:var(--ink); } h1 { font-weight:780; }
        .hero { background:linear-gradient(115deg,rgba(255,255,255,.98),rgba(224,241,236,.83)); border:1px solid var(--line); border-radius:1.25rem; padding:clamp(1.25rem,3vw,2rem); margin-bottom:1.2rem; box-shadow:0 10px 30px rgba(19,45,48,.06); }
        .eyebrow { color:var(--teal); font-weight:800; font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; }
        .hero h1 { margin:.22rem 0 .42rem; font-size:clamp(2rem,3.4vw,3rem); line-height:1.05; overflow-wrap:anywhere; }
        .hero p,.muted { color:var(--muted); line-height:1.55; }
        .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:.75rem; margin:1rem 0 1.3rem; }
        .kpi { background:var(--card); border:1px solid var(--line); border-radius:1rem; padding:1rem; min-width:0; }
        .kpi b { display:block; font-size:1.55rem; margin-top:.25rem; overflow-wrap:anywhere; }.kpi small{color:var(--muted);font-weight:650;}
        .card { background:var(--card); border:1px solid var(--line); border-radius:1rem; padding:1rem; box-shadow:0 4px 14px rgba(19,45,48,.035); }
        .product-card { min-height:13.5rem; }.product-card h3{margin:.55rem 0 .3rem;}.meta{color:var(--muted);font-size:.84rem;line-height:1.45;}
        .chip { display:inline-flex; border-radius:999px; padding:.27rem .6rem; font-size:.76rem; font-weight:750; }
        .ok { color:#08685e;background:#dcefe9; }.warn { color:#875015;background:#fae9c8; }.wait { color:#92513f;background:#f8dfd8; }.muted-chip { color:#52636b;background:#e7ecea; }.info { color:#3b657b;background:#dceaf0; }
        .bar { width:100%;height:.6rem;background:#e4ded2;border-radius:999px;overflow:hidden;margin:.7rem 0 .35rem; }.bar i{display:block;height:100%;background:var(--teal);border-radius:999px;}
        .stepper { display:flex; gap:.45rem; flex-wrap:wrap; margin:0 0 1.2rem; }.step { border-radius:999px; border:1px solid var(--line); padding:.38rem .65rem; color:var(--muted); font-size:.78rem; font-weight:700; }.step.active{background:var(--teal);color:#fff;border-color:var(--teal)}.step.done{background:#dcefe9;color:#08685e;border-color:#dcefe9}
        .action { border-left:3px solid var(--teal); padding:.85rem 1rem; background:rgba(220,239,233,.55); border-radius:0 .7rem .7rem 0; margin:.65rem 0; }
        .breadcrumb a { color:var(--teal); text-decoration:none; font-weight:700; }.breadcrumb{color:var(--muted);margin-bottom:.8rem;}
        [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:.8rem; overflow:hidden; }
        .stButton > button { border-radius:.7rem; font-weight:700; min-height:2.65rem; }.stButton > button[kind="primary"]{background:var(--teal);border-color:var(--teal)}
        @media (prefers-color-scheme:dark){:root{--ink:#e9f1ef;--muted:#b7c6c2;--paper:#132124;--card:#1b2b2e;--line:#34494c;--nav:#0c282d}.hero{background:linear-gradient(115deg,rgba(27,43,46,.99),rgba(30,64,61,.76))}.ok{color:#9be0d2;background:#1d4741}.warn{color:#ffd892;background:#534222}.wait{color:#f6b8aa;background:#4d302d}.muted-chip{color:#d0d8d5;background:#364143}.info{color:#c7e1ec;background:#29434e}}
        @media(max-width:900px){.block-container{padding:1.35rem 1rem 3rem}.hero{padding:1.25rem}.product-card{min-height:0}}
        @media(max-width:540px){.kpis{grid-template-columns:1fr}.stepper{gap:.3rem}.step{font-size:.7rem}}
        </style>
        """,
        unsafe_allow_html=True,
    )
