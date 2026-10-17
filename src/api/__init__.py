"""Local HTTP adapter for the optional React frontend (``frontend-react/``).

It exposes the existing services over JSON on 127.0.0.1 only. It holds no business logic of its
own: every route calls the same service and persistence functions the Streamlit pages call.
"""
