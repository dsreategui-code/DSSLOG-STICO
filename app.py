"""DSS Logistico - Ultima Milla Callao. Entrypoint Streamlit."""
import streamlit as st

from components.layout import (
    apply_page_config, apply_global_styles, render_app_header,
    render_view_title, render_divider, render_footer,
)
from components.buttons import secondary
from components.navigation import render_global_actions
from utils.state import init_state
from utils.constants import (
    VISTA_HOME, VISTA_VALIDATION_DATA, VISTA_VALIDATION_CONFIG, VISTA_VALIDATION_SIMULATION,
    VISTA_VALIDATION_RESULTS, VISTA_VALIDATION_EXPORT,
    VISTA_DEMO_ROLE_SELECTION, VISTA_SUPERVISOR_DATA, VISTA_SUPERVISOR_CONFIG,
    VISTA_SUPERVISOR_ROUTES, VISTA_SUPERVISOR_SIMULATION, VISTA_SUPERVISOR_ALERTS,
    VISTA_SUPERVISOR_RESULTS, VISTA_SUPERVISOR_EXPORT, VISTA_DRIVER,
    VISTA_BENCHMARK, VISTA_DIGITAL_TWIN, VISTA_PLANNING, VISTA_DEMO_FLOW,
)

from views import home as v_home
from views import demo_role_selection as v_role
from views import validation_data as v_val_data
from views import validation_config as v_val_cfg
from views import validation_simulation as v_val_sim
from views import validation_results as v_val_res
from views import validation_export as v_val_exp
from views import supervisor_data as v_sup_data
from views import supervisor_config as v_sup_cfg
from views import supervisor_routes as v_sup_routes
from views import supervisor_simulation as v_sup_sim
from views import supervisor_alerts as v_sup_alerts
from views import supervisor_results as v_sup_res
from views import supervisor_export as v_sup_exp
from views import driver_view as v_driver
from views import benchmark_svrpbench as v_bench
from views import digital_twin_view as v_twin
from views import planning_view as v_plan
from views import demo_flow as v_flow


ROUTES = {
    VISTA_HOME: v_home.render,
    VISTA_DEMO_ROLE_SELECTION: v_role.render,
    VISTA_BENCHMARK: v_bench.render,
    VISTA_DIGITAL_TWIN: v_twin.render,
    VISTA_PLANNING: v_plan.render,
    VISTA_DEMO_FLOW: v_flow.render,

    VISTA_VALIDATION_DATA: v_val_data.render,
    VISTA_VALIDATION_CONFIG: v_val_cfg.render,
    VISTA_VALIDATION_SIMULATION: v_val_sim.render,
    VISTA_VALIDATION_RESULTS: v_val_res.render,
    VISTA_VALIDATION_EXPORT: v_val_exp.render,

    VISTA_SUPERVISOR_DATA: v_sup_data.render,
    VISTA_SUPERVISOR_CONFIG: v_sup_cfg.render,
    VISTA_SUPERVISOR_ROUTES: v_sup_routes.render,
    VISTA_SUPERVISOR_SIMULATION: v_sup_sim.render,
    VISTA_SUPERVISOR_ALERTS: v_sup_alerts.render,
    VISTA_SUPERVISOR_RESULTS: v_sup_res.render,
    VISTA_SUPERVISOR_EXPORT: v_sup_exp.render,

    VISTA_DRIVER: v_driver.render,
}


def _fallback_view():
    render_view_title("Vista no disponible", "No encontramos la pantalla solicitada.")
    st.info("Volveremos a la pantalla inicial.")
    render_divider()
    if secondary("Inicio", key="fallback_back"):
        st.session_state.vista = VISTA_HOME
        st.session_state.modo = None
        st.session_state.rol = None
        st.rerun()
    render_footer()


def main():
    apply_page_config()
    apply_global_styles()
    init_state()
    render_app_header()
    render_global_actions()

    vista = st.session_state.get("vista", VISTA_HOME)
    handler = ROUTES.get(vista)
    if handler is None:
        _fallback_view()
    else:
        handler()


if __name__ == "__main__":
    main()
