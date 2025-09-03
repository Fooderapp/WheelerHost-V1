# theme.py
from PySide6 import QtWidgets, QtGui

def apply_theme(app: QtWidgets.QApplication):
    NAVY   = "#0F2431"; PANEL  = "#112B3A"; LIME   = "#D4FF00"; MUTED  = "#8BA3B0"; WHITE  = "#F2F5F8"
    base = QtGui.QFont(app.font().family(), 10); app.setFont(base)
    qss = f"""
    QWidget {{ background: {NAVY}; color: {WHITE}; font-size: 12pt; }}
    QLabel#Section {{ font-size: 11pt; color: {MUTED}; letter-spacing: 1px; font-weight: 700; }}
    QLabel#Tiny {{ font-size: 8pt; color: {MUTED}; }}
    QPushButton {{ background: transparent; color: {LIME}; border: 2px solid {LIME}; padding: 6px 14px; border-radius: 14px; }}
    QPushButton:hover {{ background: {LIME}; color: {NAVY}; }}
    QCheckBox {{ color: {WHITE}; spacing: 8px; font-weight: 700; }}
    QSlider::groove:horizontal {{ height: 12px; background: {PANEL}; border-radius: 6px; }}
    QSlider::handle:horizontal {{ width: 18px; height: 18px; margin-top: -4px; margin-bottom: -4px; border-radius: 9px; background: {LIME}; border: 2px solid {NAVY}; }}
    QProgressBar {{ background: {PANEL}; border: none; border-radius: 10px; text-align: center; height: 20px; }}
    QProgressBar::chunk {{ background: {LIME}; border-radius: 10px; }}
    QPlainTextEdit {{ background: {PANEL}; border: none; border-radius: 10px; padding: 8px; color: {WHITE}; font-size: 10pt; }}
    .Led {{ background: #233747; border-radius: 12px; min-width: 44px; min-height: 32px; border: 2px solid #233747; }}
    .Led[on="true"] {{ background: {LIME}; border: 2px solid {LIME}; }}
    """
    app.setStyleSheet(qss)
