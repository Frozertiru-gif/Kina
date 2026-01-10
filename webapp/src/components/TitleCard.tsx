import { Link } from "react-router-dom";
import type { Title } from "../api/types";

interface TitleCardProps {
  title: Title;
  isFavorite: boolean;
  onToggleFavorite: () => void;
}

export const TitleCard = ({ title, isFavorite, onToggleFavorite }: TitleCardProps) => {
  return (
    <article className="title-card">
      <Link className="title-card__poster" to={`/title/${title.id}`}>
        <img src={title.poster_url || "/placeholder-poster.svg"} alt={title.name} />
        <span className="title-card__badge">
          {title.type === "movie" ? "Фильм" : "Сериал"}
        </span>
      </Link>
      <div className="title-card__body">
        <div>
          <strong className="title-card__name">{title.name}</strong>
          <div className="meta">{title.year || "—"}</div>
        </div>
        <button className="favorite-toggle" type="button" onClick={onToggleFavorite}>
          {isFavorite ? "⭐ В избранном" : "☆ В избранное"}
        </button>
      </div>
      <Link className="button ghost" to={`/title/${title.id}`}>
        Подробнее
      </Link>
    </article>
  );
};
