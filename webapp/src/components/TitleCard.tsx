import { Link } from "react-router-dom";
import type { Title } from "../api/types";

interface TitleCardProps {
  title: Title;
  isFavorite: boolean;
  onToggleFavorite: () => void;
}

export const TitleCard = ({ title, isFavorite, onToggleFavorite }: TitleCardProps) => {
  return (
    <div className="title-card">
      <Link to={`/title/${title.id}`}>
        <img src={title.poster_url || "/placeholder-poster.svg"} alt={title.name} />
      </Link>
      <div>
        <strong>{title.name}</strong>
        <div className="meta">
          {title.year || "—"} • {title.type === "movie" ? "Movie" : "Series"}
        </div>
      </div>
      <div className="title-actions">
        <Link className="button secondary" to={`/title/${title.id}`}>
          Подробнее
        </Link>
        <button className="icon-button" onClick={onToggleFavorite}>
          {isFavorite ? "⭐" : "☆"}
        </button>
      </div>
    </div>
  );
};
