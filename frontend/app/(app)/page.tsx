import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { Activity, Database, ShieldAlert, TimerReset } from "lucide-react";

const overview = [
  { label: "Новых аномалий", value: "—", icon: ShieldAlert, detail: "После первого анализа" },
  { label: "Запусков анализа", value: "—", icon: Activity, detail: "История пока пуста" },
  { label: "Загружено данных", value: "—", icon: Database, detail: "Добавьте SIEM/NGFW логи" },
  { label: "Среднее время", value: "—", icon: TimerReset, detail: "Появится после запусков" },
];

export default function OverviewPage() {
  return (
    <div className="page-stack">
      <PageHeader
        title="Центр мониторинга"
        description="Единая точка контроля загрузок, ML-запусков и расследований."
      />
      <section className="metric-grid" aria-label="Ключевые показатели">
        {overview.map(({ label, value, icon: Icon, detail }) => (
          <Card key={label} className="metric-card">
            <span className="metric-icon">
              <Icon aria-hidden="true" />
            </span>
            <p>{label}</p>
            <strong>{value}</strong>
            <small>{detail}</small>
          </Card>
        ))}
      </section>
      <Card className="hero-panel">
        <div>
          <p className="section-label">Начало работы</p>
          <h2>Загрузите данные для первого анализа</h2>
          <p>Платформа проверит структуру логов, нормализует события и запустит поиск аномалий.</p>
        </div>
        <ol className="step-list">
          <li>
            <span>01</span>
            <div>
              <strong>Загрузка</strong>
              <small>CSV, TSV или TXT до 50 МиБ</small>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>Нормализация</strong>
              <small>Проверка колонок и разделение по датам</small>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>Анализ</strong>
              <small>Скоринг пользователей и хостов</small>
            </div>
          </li>
        </ol>
      </Card>
    </div>
  );
}
